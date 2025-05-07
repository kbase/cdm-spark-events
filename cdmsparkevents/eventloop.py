"""
The main event loop for the event handler.
"""


from kafka import KafkaConsumer
import logging

from cdmsparkevents.config import Config


def get_kafka_consumer_from_config(config: Config) -> KafkaConsumer:
    """
    Get a Kafka consumer from a validated configuration. No further validation is performed.
    
    The consumer is set up with auto commit disabled.
    """
    return KafkaConsumer(
        config.kafka_topic_jobs,
        bootstrap_servers=config.kafka_bootstrap_servers.split(","),
        group_id=config.kafka_group_id,
        enable_auto_commit=False,
        max_poll_interval_ms=config.kafka_max_poll_interval_ms,
        # If no partion offsets exist for the group, go to the earliest record
        auto_offset_reset="earliest",
    )


def run_event_loop(config: Config, consumer: KafkaConsumer = None):
    """
    Run the event loop with the given events processor configuration. If a consumer is not
    provided (recommended), it is generated via the get_kafka_consumer_from_config() method.
    In almost all cases (unit tests being an exception), this option should be preferred.
    """
    if not consumer:
        consumer = get_kafka_consumer_from_config(config)
    logr = logging.getLogger(__name__)
    for msg in consumer:
        logr.info(str(msg))
        # TODO NEXT process message - pull job from CTS, etc.
        # TODO NEXT handle errors - put errored messages on DLQ. Add retries later
        # TODO NEXT set up spark context and run configured code based on image
        
        consumer.commit()
