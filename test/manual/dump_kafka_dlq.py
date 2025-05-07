"""
Writes the current contents of the Kafka CDM Task Service Deat Letter Queue topic in their entirety
to stdout.

Assuming a docker compose context, invoke like:

docker compose exec cdm_events python test/manual/dump_kafka_dlq.py
"""

# Probably some useful options we could add here, like a group ID to only see new messages, etc.


from kafka import KafkaConsumer
from pprint import pprint

from cdmsparkevents.config import Config


def main():
    cfg = Config()
    cons = KafkaConsumer(
        cfg.kafka_topic_jobs_dlq,
        bootstrap_servers=cfg.kafka_bootstrap_servers.split(","),
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    pollres = True
    try:
        while pollres:
            pollres = cons.poll(timeout_ms=2000)
            for _, messages in pollres.items():
                for msg in messages:
                    # https://docs.python.org/3/library/collections.html#collections.somenamedtuple._asdict
                    pprint(msg._asdict())
    finally:
        cons.close()


if __name__ == "__main__":
    main()
