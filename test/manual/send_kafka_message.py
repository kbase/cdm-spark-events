"""
Sends a message to the configured Kafka instance.

Assuming a docker compose context, invoke like:

docker compose exec cdm_events python test/manual/send_kafka_message.py -t <message_text>
"""

# TODO CTS send a message in CTS format


from kafka import KafkaProducer
import sys

from cdmsparkevents.config import Config


def main():
    # TODO CTS use argparse when we have more than one argument
    if sys.argv[1] != "-t":
        raise ValueError(f"Unknown option: {sys.argv[1]}")
    cfg = Config()
    prod = KafkaProducer(
        bootstrap_servers=cfg.kafka_bootstrap_servers.split(","),
        enable_idempotence=True,
        acks='all',
    )
    fut = prod.send(cfg.kafka_topic_jobs, sys.argv[2].encode("utf-8"))
    fut.get(timeout=10)  # ensure message is sent


if __name__ == "__main__":
    main()
