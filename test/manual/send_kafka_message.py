"""
Sends a message to the configured Kafka instance.

Assuming a docker compose context, invoke like:

docker compose exec cdm_events python test/manual/send_kafka_message.py -t <message_text>
"""

# TODO CTS send a message in CTS format - eh, this is actually really easy as is. Probably YAGNI


from kafka import KafkaProducer
import os
import sys

from cdmsparkevents.config import Config


def main():
    # TODO CTS use argparse when we have more than one argument
    if sys.argv[1] != "-t":
        raise ValueError(f"Unknown option: {sys.argv[1]}")
    # prevent config errors if the token is passed via a file vs. env var
    os.environ["CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN"] = "foo"
    cfg = Config()
    prod = KafkaProducer(
        bootstrap_servers=cfg.kafka_bootstrap_servers.split(","),
        enable_idempotence=True,
        acks='all',
    )
    try:
        fut = prod.send(cfg.kafka_topic_jobs, sys.argv[2].encode("utf-8"))
        fut.get(timeout=10)  # ensure message is sent
    finally:
        prod.close()


if __name__ == "__main__":
    main()
