"""
The main event loop for the event handler.
"""


import json
from kafka import KafkaConsumer, KafkaProducer, TopicPartition, OffsetAndMetadata
from kafka.consumer.fetcher import ConsumerRecord
import logging
import signal
import threading

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
        self._cfg = config
        self._cons = consumer if consumer else get_kafka_consumer_from_config(config)
        try:
            self._dlq = dlq_producer if dlq_producer else get_kafka_dlq_producer_from_config(
                config
            )
        except:
            self._cons.close()
        self._log = logging.getLogger(__name__)

    _REQUIRED_JOB_MSG_FIELDS = {"job_id", "state"}  # don't need the other two for now

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
        except Exception as e:
            self._log.exception(f"Unable to deserialize message:\n{msg.value}")
            self._send_to_dlq_and_commit(msg)
            return
        if self._REQUIRED_JOB_MSG_FIELDS - val.keys():
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
    
        # TODO NEXT process message - pull job from CTS, etc.
        # TODO NEXT handle errors - put errored messages on DLQ. Add retries later
        # TODO NEXT set up spark context and run configured code based on image
        
        self._commit(msg)

    def close(self):
        self._cons.close()
        self._dlq.close()
