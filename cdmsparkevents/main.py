"""
Main class for the events system. Gets the config and starts the event loop.
"""

import datetime
import logging
from pythonjsonlogger.core import RESERVED_ATTRS
from pythonjsonlogger.json import JsonFormatter

from cdmsparkevents.config import Config
from cdmsparkevents.eventloop import run_event_loop


# httpx is super chatty if the root logger is set to INFO
logging.basicConfig(level=logging.WARNING)
# https://stackoverflow.com/a/58777937/643675
logging.Formatter.formatTime = (
    lambda self, record, datefmt=None: datetime.datetime.fromtimestamp(
        record.created, datetime.timezone.utc
    ).astimezone().isoformat(sep="T",timespec="milliseconds"))
rootlogger = logging.getLogger()
# Remove any existing handlers. The list slice prevents list modification while iterating
for handler in rootlogger.handlers[:]:
    rootlogger.removeHandler(handler)

handler = logging.StreamHandler()


class CustomJsonFormatter(JsonFormatter):
    """ Remove keys with null values from the logs. """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def process_log_record(self, log_record):
        return super().process_log_record(
            {k: v for k, v in log_record.items() if v is not None}
        )


handler.setFormatter(CustomJsonFormatter(
    "{levelname}{name}{message}{asctime}{exc_info}",
    style="{",
    rename_fields={"levelname": "level"},
    reserved_attrs=RESERVED_ATTRS + ["color_message"],
))
rootlogger.addHandler(handler)
logging.getLogger("cdmsparkevents").setLevel(logging.INFO)


def main():
    cfg = Config()
    # Can't use __name__ here since we're expecting to be run as a script, where the name is just
    # __main__
    logging.getLogger("cdmsparkevents.main").info("Service configuration", extra=cfg.safe_dump())
    run_event_loop(cfg)


if __name__ == "__main__":
    main()
