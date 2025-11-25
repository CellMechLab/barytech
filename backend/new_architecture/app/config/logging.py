"""
Logging Configuration
Centralized logging setup to prevent Kafka debug spam
"""

import logging


def configure_logging():
    """
    Configure logging levels for the application.
    This should be called before importing any modules to prevent Kafka debug spam.
    """
    # 🔇 CRITICAL: Set logging levels BEFORE importing any modules
    # This prevents Kafka debug spam from appearing
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("aiokafka").setLevel(logging.WARNING)
    logging.getLogger("aiokafka.consumer").setLevel(logging.WARNING)
    logging.getLogger("aiokafka.producer").setLevel(logging.WARNING)
    logging.getLogger("aiokafka.conn").setLevel(logging.WARNING)
    logging.getLogger("aiokafka.consumer.fetcher").setLevel(logging.WARNING)
    logging.getLogger("aiokafka.consumer.group_coordinator").setLevel(logging.WARNING)
    logging.getLogger("aiokafka.producer.sender").setLevel(logging.WARNING)
    logging.getLogger("kafka").setLevel(logging.WARNING)

    # Keep application logs at INFO level
    logging.getLogger("app").setLevel(logging.INFO)
    logging.getLogger(__name__).setLevel(logging.INFO)

