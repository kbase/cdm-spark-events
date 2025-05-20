"""
The main event loop for the event handler.
"""


import importlib
import json
from kafka import KafkaConsumer, KafkaProducer, TopicPartition, OffsetAndMetadata
from kafka.consumer.fetcher import ConsumerRecord
import logging
from pyspark.sql import SparkSession
import requests
import signal
import time
import uuid
import threading
from typing import Any

from cdmsparkevents.config import Config
from cdmsparkevents.spark import spark_session


def get_kafka_consumer_from_config(config: Config) -> KafkaConsumer:
    """
    Get a Kafka consumer from a validated configuration. No further validation is performed.
    
    The consumer is set up with auto commit disabled.
    """
    return KafkaConsumer(
        config.kafka_topic_jobs,
        # can't test multiple servers without a massive PITA
        bootstrap_servers=config.kafka_bootstrap_servers.split(","),
        group_id=config.kafka_group_id,
        enable_auto_commit=False,
        max_poll_interval_ms=config.kafka_max_poll_interval_ms,
        # If no partiton offsets exist for the group, go to the earliest record
        auto_offset_reset="earliest",
    )


def get_kafka_dlq_producer_from_config(config: Config) -> KafkaProducer:
    """
    Get a Kafka producer for the Dead Letter Queue from a validated configuration.
    No further validation is performed.
    """
    return KafkaProducer(
        # can't test multiple servers without a massive PITA
        bootstrap_servers=config.kafka_bootstrap_servers.split(','),
        enable_idempotence=True,
        acks='all',
    )


shutdown_event = threading.Event()


def handle_signal(signum, frame):
    logging.getLogger(__name__).info(f"Received signal {signum}, shutting down...")
    shutdown_event.set()


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


class EventLoop:
    """
    The event loop for handling CDM Task Service events.
    """
    
    def __init__(
        self,
        config: Config,
        consumer: KafkaConsumer = None,
        dlq_producer: KafkaProducer = None,
    ):
        """
        Create the event loop with the given events processor configuration.
        
        config - the event processor configuration.
        consumer - the consumer to use to read the CDM Task Service Kafka stream. If a consumer is
            not provided (recommended), it is generated via the get_kafka_consumer_from_config()
            method.
            In almost all cases (unit tests being an exception), this option should be preferred.
        dlq_producer - A Kafka Producer for sending failed consumer messages to the Dead Letter
            Queue. If a producer is not provided (recommended), it generated via the
            get_kafka_dlq_producer_from_config() method.
            In almost all cases (unit tests being an exception), this option should be preferred.
        """
        if not config:
            raise ValueError("config required")
        self._log = logging.getLogger(__name__)
        self._cfg = config
        self._headers = {"Authorization": f"Bearer {self._cfg.cdm_task_service_admin_token}"}
        self._test_cts_connection()
        self._cons = consumer if consumer else get_kafka_consumer_from_config(config)
        try:
            self._dlq = dlq_producer if dlq_producer else get_kafka_dlq_producer_from_config(
                config
            )
        except:
            self._cons.close()

    _REQUIRED_CTS_JOB_MSG_FIELDS = {"job_id", "state"}  # don't need the other two for now

    def _test_cts_connection(self):
        self._log.info("Checking CTS connection")
        res = self._cts_request("")
        # TODO SOON Get rid of the prototype in the name and add a notes field or something so this
        #           doesn't break later
        if res.get("service_name") != "CDM Task Service Prototype":
            self._log.error(f"Unexpected response from the CTS:\n{res}")
            raise ValueError(
                f"The CTS url {self._cfg.cdm_task_service_url} does not appear "
                + "to point to the CTS service"
            )
        # test the token has admin privs
        self._cts_request("admin/jobs?limit=1")
        self._log.info("Done checking CTS connection")

    def _request_job(self, job_id: str) -> dict[str, Any]:
        return self._cts_request(f"admin/jobs/{job_id}")

    def _cts_request(self, url_path: str) -> dict[str, Any]:
        # may need to use requests-mock to test this fn
        # This fn will probably need changes as we discover error modes we've missed or
        # miscategorized as fatal or recoverable 
        res = requests.get(self._cfg.cdm_task_service_url + "/" + url_path, headers=self._headers)
        if 400 <= res.status_code < 500:
            try:
                err = res.json()
            except Exception as e:
                self._log.exception(f"Unparseable error response from the CTS:\n{res.text}")
                raise _FatalError(
                    f"Unparseable error response ({res.status_code}) from the CTS"
                ) from e
            if "error" not in err:
                self._log.error(f"Unexpected error structure from the CTS:\n{err}")
                raise _FatalError(
                    f"Unexpected error structure, response ({res.status_code}) from the CTS"
                )
            if err["error"].get("appcode") == 40040:
                raise _NoJobError()
            self._log.error(f"Unrecoverable error response from the CTS:\n{err}")
            raise _FatalError(f"Unrecoverable error response ({res.status_code}) from the CTS")
        if res.status_code >= 500:
            # There's some 5XX errors that probably aren't recoverable but I've literally never
            # seem them in practice
            self._log.error(f"Error response from the CTS:\n{res.text}")
            raise _PotentiallyRecoverableError(
                f"Error response ({res.status_code}) from the CTS"
            )
        if not (200 <= res.status_code < 300):
            self._log.error(f"Unexpected response from the CTS:\n{res.text}")
            raise _FatalError(f"Unexpected response ({res.status_code}) from the CTS")
        try:
            return res.json()
        except Exception as e:
            self._log.exception(f"Unparseable response from the CTS:\n{res.text}")
            raise _FatalError("Unparseable response from the CTS") from e

    def _send_to_dlq_and_commit(self, msg: ConsumerRecord, new_value: bytes = None):
        fut = self._dlq.send(self._cfg.kafka_topic_jobs_dlq, new_value or msg.value)
        fut.get(timeout=10)  # ensure message is sent
        self._commit(msg)

    def _commit(self, msg: ConsumerRecord):
        # Older versions of Kafka don't support leader epoch, so default to unknown in that case
        # Testing this would be really painful
        le = -1 if msg.leader_epoch is None else msg.leader_epoch
        self._cons.commit({
            TopicPartition(topic=msg.topic, partition=msg.partition):
                OffsetAndMetadata(msg.offset + 1, None, le)
        })

    def start_event_loop(self):
        """
        Start the event loop.
        """
        self._log.info("Starting event loop")
        while not shutdown_event.is_set():
            pollres = self._cons.poll(timeout_ms=1000)
            for _, messages in pollres.items():
                for msg in messages:
                    self._process_message(msg)

    # TODO TEST write a test making sure that the offset commit is working correctly
    #           this could be tricky... need to start / stop the event loop. Manual testing
    #           appears to work

    def _process_message(self, msg):
        # We expect that the data processing time will be much greater than any time spent
        # dealing with the Kafka message, so we commit after every message to avoid having
        # to reprocess the entire batch of messages from poll() if a failure occurs.
        # Note this may result in non-zero lag in some circumstances:
        # https://www.confluent.io/blog/guide-to-consumer-offsets/
        try:
            val = json.loads(msg.value.decode("utf-8"))
        except Exception:
            self._log.exception(f"Unable to deserialize message:\n{msg.value}")
            self._send_to_dlq_and_commit(msg)
            return
        if val.get("special_event_type") == "integration_test":
            self._run_integration_test(val)
            self._commit(msg)
            return
        if self._REQUIRED_CTS_JOB_MSG_FIELDS - val.keys():
            err = f"Message has missing required keys:\n{val}"
            self._log.error(err)
            val["error_dlq"] = err
            self._send_to_dlq_and_commit(msg, new_value=json.dumps(val).encode("utf-8"))
            return
        job_id = val["job_id"]
        if val["state"] != "complete":
            self._log.info(
                f"Discarding CTS job transition to state {val['state']} for job {job_id}"
            )
            self._commit(msg)
            return
        
        self._log.info(f"Processing completed CTS job {job_id}")
        try:
            job_info = self._get_job_info(job_id)
        except _NoJobError:
            self._log.error(f"No such job: {job_id}")
            val["error_dlq"] = "No such job"
            self._send_to_dlq_and_commit(msg, new_value=json.dumps(val).encode("utf-8"))
            return
        self._log.info(job_info)
        # TODO NEXT call _run_importer here after cutting down the job info to what's necessary
        #           make sure to try / catch and dlq failures
    
        # TODO NEXT process message - pull job from CTS, etc.
        # TODO NEXT handle errors - put errored messages on DLQ. Add retries later
        # TODO NEXT set up spark context and run configured code based on image
        
        self._commit(msg)

    _EXP_BACKOFF = [1, 2, 5, 10, 30, 60, 120, 300, 600, -1]

    def _get_job_info(self, job_id: str):
        # If the CTS is unreachable, we don't want to keep sticking messages on the DLQ over and
        # over. As such, we try for several minutes to get the job info and then throw an
        # exception and bail out, stopping the event loop.
        for slp in self._EXP_BACKOFF:
            try:
                return self._request_job(job_id)
            except _NoJobError:
                raise
            except _FatalError:
                raise
            except Exception:
                if slp > 0:
                    self._log.info(f"Error contacting the CTS server, retrying in {slp}s")
                    time.sleep(slp)
        raise _FatalError(
            f"Failed to connect to the CTS server after {len(self._EXP_BACKOFF) - 1} "
            + f"attempts over {sum(self._EXP_BACKOFF) + 1}s, bailing out"
        )
        
    def _run_integration_test(self, val: dict[str, Any]):
        app_prefix = val.get("app_name_prefix") or "integration_test"
        app_name = f"{app_prefix}_{uuid.uuid4()}"
        self._log.info(f"Running integration test with app {app_name}")
        try:
            self._run_importer("cdmsparkevents.selftest.integration", app_name, val)
        except Exception as e:
            self._log.exception(
                f"Integration test failed for {app_name}: {e}",
                extra={"event": val},
            )

    def _run_importer(self, importer_module: str, app_name: str, job_info: dict[str, Any]):
        mod = importlib.import_module(importer_module)
        sparkcapture = []
        def get_spark(*, executor_cores: int = 1) -> SparkSession:
            spark = spark_session(self._cfg, app_name, executor_cores=executor_cores)
            sparkcapture.append(spark)
            return spark
        try:
            mod.run_import(get_spark, job_info)
        finally:
            if sparkcapture:
                sparkcapture[0].stop()

    def close(self):
        self._cons.close()
        self._dlq.close()


class _NoJobError(Exception): pass


class _PotentiallyRecoverableError(Exception): pass


class _FatalError(Exception): pass
