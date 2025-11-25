"""
Batch Processing Configuration
Optimized settings for high-throughput data ingestion
"""

import os

# Database batch settings - ULTRA-OPTIMIZED for ultra-high throughput (10k+ points/sec)
DB_BATCH_SIZE = int(
    os.getenv("DB_BATCH_SIZE", "10000")
)  # Target batch size for database saves (increased for ultra-high throughput)
DB_MIN_BATCH_SIZE = int(
    os.getenv("DB_MIN_BATCH_SIZE", "50")
)  # Minimum batch size before timeout (lowered to flush small tails fast)
DB_BATCH_TIMEOUT = float(
    os.getenv("DB_BATCH_TIMEOUT", "0.1")
)  # Timeout in seconds (reduced to 100ms for faster flushes)
DB_CHUNK_SIZE = int(os.getenv("DB_CHUNK_SIZE", "10000"))  # Database insert chunk size

# Parallel save workers configuration
N_SAVE_WORKERS = int(
    os.getenv("N_SAVE_WORKERS", "3")
)  # Number of parallel save workers per device

# WebSocket batch settings
WS_BATCH_SIZE = int(
    os.getenv("WS_BATCH_SIZE", "10000")
)  # WebSocket broadcast batch size
WS_BATCH_TIMEOUT = float(
    os.getenv("WS_BATCH_TIMEOUT", "0.01")
)  # WebSocket batch timeout

# Kafka batch settings
KAFKA_BATCH_SIZE = int(
    os.getenv("KAFKA_BATCH_SIZE", "32768")
)  # Kafka producer batch size

# Performance monitoring
ENABLE_BATCH_LOGGING = os.getenv("ENABLE_BATCH_LOGGING", "true").lower() == "true"
LOG_EVERY_N_BATCHES = int(os.getenv("LOG_EVERY_N_BATCHES", "10"))  # Log every Nth batch


def get_batch_config():
    """Get current batch configuration"""
    return {
        "db_batch_size": DB_BATCH_SIZE,
        "db_min_batch_size": DB_MIN_BATCH_SIZE,
        "db_batch_timeout": DB_BATCH_TIMEOUT,
        "db_chunk_size": DB_CHUNK_SIZE,
        "ws_batch_size": WS_BATCH_SIZE,
        "ws_batch_timeout": WS_BATCH_TIMEOUT,
        "kafka_batch_size": KAFKA_BATCH_SIZE,
        "enable_batch_logging": ENABLE_BATCH_LOGGING,
        "log_every_n_batches": LOG_EVERY_N_BATCHES,
    }


def print_batch_config():
    """Print current batch configuration"""
    config = get_batch_config()
    print("📊 Batch Processing Configuration:")
    for key, value in config.items():
        print(f"   {key}: {value}")

