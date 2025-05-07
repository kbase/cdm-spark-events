"""
The main event loop for the event handler.
"""


import json
from kafka import KafkaConsumer, KafkaProducer
import logging

from cdmsparkevents.config import Config


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
        self._cfg = config
        self._cons = consumer if consumer else get_kafka_consumer_from_config(config)
        self._dlq = dlq_producer if dlq_producer else get_kafka_dlq_producer_from_config(config)


    _REQUIRED_JOB_MSG_FIELDS = {"job_id", "state"}  # don't need the other two for now


    def _send_to_dlq_and_commit(self, value: bytes):
        fut = self._dlq.send(self._cfg.kafka_topic_jobs_dlq, value)
        fut.get(timeout=10)  # ensure message is sent
        self._cons.commit()


    def start_event_loop(self):
        """
        Start the event loop.
        """
        logr = logging.getLogger(__name__)
        # TODO SHUTDOWN switch to poll() and add signal handlers to shutdown on sigterm
        # Add a try finally in main to close the event loop
        for msg in self._cons:
            try:
                val = json.loads(msg.value.decode("utf-8"))
            except Exception as e:
                logr.exception(f"Unable to deserialize message:\n{msg.value}")
                self._send_to_dlq_and_commit(msg.value)
                continue
            if self._REQUIRED_JOB_MSG_FIELDS - val.keys():
                err = f"Message has missing required keys:\n{val}"
                logr.error(err)
                val["error_dlq"] = err
                self._send_to_dlq_and_commit(json.dumps(val).encode("utf-8"))
                continue
            job_id = val["job_id"]
            if val["state"] != "complete":
                logr.info(
                    f"Discarding CTS job transition to state {val['state']} for job {job_id}"
                )
                self._cons.commit()
                continue
            
            logr.info(f"Processing completed CTS job {job_id}")
    
            # TODO NEXT process message - pull job from CTS, etc.
            # TODO NEXT handle errors - put errored messages on DLQ. Add retries later
            # TODO NEXT set up spark context and run configured code based on image
            
            self._cons.commit()
