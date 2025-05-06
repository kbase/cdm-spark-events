"""
Main class for the events system. Gets the config and starts the event loop.
"""

from kafka import KafkaConsumer

from cdmsparkevents.config import Config


def main():
    cfg = Config()
    print(cfg)


if __name__ == "__main__":
    main()
