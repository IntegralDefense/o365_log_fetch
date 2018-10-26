import logging
import os


def setup_logger(log_level=None, log_location=None):
    log_path = log_location or os.environ.get("O365_DEBUG_LOG_LOCATION")
    log_file = os.path.join(log_path, "debug.log")
    handler = logging.FileHandler(log_file)
    formatter = logging.Formatter("%(asctime)s;%(levelname)s:%(name)s:%(message)s")
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(log_level or os.environ.get("LOG_LEVEL", "INFO"))
    root.addHandler(handler)
