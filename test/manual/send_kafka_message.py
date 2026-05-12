"""
Sends a message to the configured Kafka instance.

Assuming a docker compose context, invoke like:

docker compose exec cdm-events python test/manual/send_kafka_message.py -t <message_text>
"""

# TODO CTS send a message in CTS format - eh, this is actually really easy as is. Probably YAGNI
import os
import sys

from kafka import KafkaProducer

from cdmsparkevents.config import Config


def _load_secret_from_file(env_var: str, file_env_var: str):
    if os.environ.get(env_var) or not os.environ.get(file_env_var):
        return
    with open(os.environ[file_env_var], encoding="utf-8") as handle:
        os.environ[env_var] = handle.read().strip()


def main():
    # TODO CTS use argparse when we have more than one argument
    if sys.argv[1] != "-t":
        raise ValueError(f"Unknown option: {sys.argv[1]}")
    # prevent config errors if the token is passed via a file vs. env var
    os.environ.setdefault("CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN", "foo")
    _load_secret_from_file("CSEP_POLARIS_CREDENTIAL", "CSEP_POLARIS_CREDENTIAL_FILE")
    cfg = Config()
    prod = KafkaProducer(
        bootstrap_servers=cfg.kafka_bootstrap_servers.split(","),
        enable_idempotence=True,
        acks="all",
    )
    try:
        fut = prod.send(cfg.kafka_topic_jobs, sys.argv[2].encode("utf-8"))
        fut.get(timeout=10)  # ensure message is sent
    finally:
        prod.close()


if __name__ == "__main__":
    main()
