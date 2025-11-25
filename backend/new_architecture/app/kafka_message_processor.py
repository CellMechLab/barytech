"""
Kafka-based Message Processor
Alternative to direct processing - uses Kafka for persistence and scalability
"""

import asyncio
import json
import logging
import time
from collections import deque
from typing import Dict

import app.shared_state
from app.kafka_client import get_kafka_stats, start_kafka_consumer_for_device
from app.config.kafka_topics import get_all_device_ids
from app.message_processor import (
    device_config,
    device_queues,
    device_save_queues,
    processing_counters,
    start_device_broadcaster,
    start_device_saver,
)
from app.utils_compress import sniff_codec_from_magic

logger = logging.getLogger(__name__)

# Track last time we saw data for each device (used by health monitoring)
last_seen: Dict[str, float] = {}

# Track active Kafka consumers
active_kafka_consumers: Dict[str, bool] = {}

# ✅ Consumer health monitoring
consumer_health_stats: Dict[str, Dict] = {}


async def kafka_message_handler_compressed(
    device_id: str, raw_payload: bytes, headers: dict = None
):
    """
    Handle compressed messages from Kafka - forward compressed bytes to WebSocket
    and optionally decompress for database saving
    """
    try:
        logger.info(
            f"📥 Kafka consumer received compressed message for device {device_id}: {len(raw_payload)} bytes"
        )

        # Extract compression info from headers
        codec = None
        if headers:
            codec = (
                headers.get("content-encoding", b"").decode()
                if isinstance(headers.get("content-encoding"), bytes)
                else headers.get("content-encoding")
            )

        # Fallback to magic header detection
        if not codec:
            codec = sniff_codec_from_magic(raw_payload)

        # Update last-seen timestamp
        last_seen[device_id] = time.time()

        # Initialize device config if needed (for device tracking, not save_flag)
        if device_id not in device_config:
            device_config[device_id] = {}

        # Ensure broadcaster is started for this device
        await start_device_broadcaster(device_id)

        # Always forward compressed bytes into the device queue
        try:
            compressed_message = {
                "type": "compressed_data",
                "device_id": device_id,
                "codec": codec,
                "data": raw_payload.hex(),  # hex string for JSON transport
                "size": len(raw_payload),
            }
            device_queues[device_id].put_nowait(compressed_message)
            logger.debug(
                f"📤 Forwarded compressed data to broadcast queue for device {device_id}"
            )
        except asyncio.QueueFull:
            logger.warning(
                f"⚠️ Broadcast queue full for device {device_id}, dropping compressed payload"
            )
            try:
                from app.metrics import BROADCAST_QUEUE_DROPPED

                BROADCAST_QUEUE_DROPPED.labels(device_id=device_id).inc()
            except ImportError:
                pass

        # Save to database if per-device save flag is enabled (decompress only here)
        # Check save mode from shared_state (set via WebSocket "save" message)
        if app.shared_state.is_save_enabled(device_id):
            await start_device_saver(device_id)
            try:
                # Decompress for database saving
                from app.utils_compress import safe_json_loads

                decompressed_data = safe_json_loads(raw_payload, codec)

                # Convert to list if single object
                if not isinstance(decompressed_data, list):
                    decompressed_data = [decompressed_data]

                # Queue for database saving
                points_count = len(decompressed_data)
                enqueued_count = 0
                for message in decompressed_data:
                    try:
                        device_save_queues[device_id].put_nowait(message)
                        enqueued_count += 1
                    except asyncio.QueueFull:
                        logger.warning(
                            f"⚠️ [{device_id}] Save queue full, dropped decompressed message"
                        )
                        try:
                            from app.metrics import SAVE_QUEUE_DROPPED

                            SAVE_QUEUE_DROPPED.labels(device_id=device_id).inc()
                        except ImportError:
                            pass
                        break
                
                # Log successful enqueue if we enqueued any points
                if enqueued_count > 0:
                    logger.debug(
                        f"💾 Enqueued {enqueued_count} points for DB save for device {device_id}"
                    )

            except Exception as e:
                logger.error(f"❌ Error decompressing for database save: {e}")

        # Update processing counters
        processing_counters.device_processed += 1

    except Exception as e:
        logger.error(
            f"❌ Error processing compressed Kafka message for device {device_id}: {e}"
        )


async def kafka_message_handler(device_id: str, records: list):
    """
    Handle messages consumed from Kafka topics.
    This replaces the direct MQTT to device queue flow.
    Robustly handles bytes, strings, or dicts from Kafka consumer.
    """
    try:
        logger.info(
            "📥 Kafka consumer received %d messages for device %s",
            len(records),
            device_id,
        )

        decoded_payloads = []

        for r in records:
            raw = getattr(
                r, "value", r
            )  # sometimes consumer gives objects, sometimes already values

            # Extract compression info from headers if available
            codec = None
            if hasattr(r, "headers") and r.headers:
                headers_dict = dict(r.headers) if r.headers else {}
                codec_header = headers_dict.get("content-encoding")
                if codec_header:
                    codec = (
                        codec_header.decode()
                        if isinstance(codec_header, bytes)
                        else codec_header
                    )

            # 1) bytes → decode and json.loads (handle compression if needed)
            if isinstance(raw, (bytes, bytearray)):
                try:
                    # Check for compression and decompress if needed
                    if codec or sniff_codec_from_magic(raw):
                        from app.utils_compress import safe_json_loads

                        decoded = safe_json_loads(raw, codec)
                    else:
                        decoded = json.loads(raw.decode("utf-8"))
                except Exception:
                    logger.exception(
                        "❌ Failed to json-decode bytes payload for device %s",
                        device_id,
                    )
                    continue

            # 2) str → json.loads (if it's JSON) or treat as error
            elif isinstance(raw, str):
                try:
                    decoded = json.loads(raw)
                except Exception:
                    logger.error(
                        "❌ Got string payload that is not valid JSON for device %s: %r",
                        device_id,
                        raw[:200],
                    )
                    continue

            # 3) already a dict/list → keep as is
            else:
                decoded = raw

            # Handle both dict and list payloads (list = batch of messages)
            if isinstance(decoded, list):
                # Batch payload - add each item
                for item in decoded:
                    if isinstance(item, dict):
                        decoded_payloads.append(item)
                    else:
                        logger.error(
                            "❌ Unexpected item type %s in list payload for device %s, expected dict; item=%r",
                            type(item),
                            device_id,
                            str(item)[:200],
                        )
            elif isinstance(decoded, dict):
                # Single message payload
                decoded_payloads.append(decoded)
            else:
                logger.error(
                    "❌ Unexpected payload type %s for device %s, expected dict or list; payload=%r",
                    type(decoded),
                    device_id,
                    str(decoded)[:200],
                )
                continue

        if not decoded_payloads:
            logger.warning(
                "⚠️ No valid payloads after decoding for device %s", device_id
            )
            return

        # From here on, always work with dicts
        batch_data = decoded_payloads

        # ✅ Update last-seen timestamp for health monitoring
        last_seen[device_id] = time.time()

        # ✅ Track end-to-end latency for Kafka messages
        # (disabled: latency_tracker no longer exists in new architecture)
        # from app.message_processor import latency_tracker
        #
        # for message in batch_data:
        #     message_timestamp = latency_tracker.parse_timestamp(message)
        #     if message_timestamp:
        #         latency = time.time() - message_timestamp
        #         latency_tracker.record_latency(latency, "kafka_per_device")

        # Initialize device config if needed (for device tracking, not save_flag)
        if device_id not in device_config:
            device_config[device_id] = {}

        # Ensure broadcaster is started for this device
        await start_device_broadcaster(device_id)

        # Put messages in device queue for broadcasting (same as direct processing)
        if device_id not in device_queues:
            from app.message_processor import MAX_DEVICE_QUEUE_SIZE

            device_queues[device_id] = asyncio.Queue(maxsize=MAX_DEVICE_QUEUE_SIZE)

        # ✅ OPTIMIZED: Process messages in larger chunks to reduce overhead
        chunk_size = 1000  # Process 1000 messages at a time
        for chunk_start in range(0, len(batch_data), chunk_size):
            chunk = batch_data[chunk_start : chunk_start + chunk_size]

            # Try to add the entire chunk at once
            try:
                for message in chunk:
                    device_queues[device_id].put_nowait(message)
                    # MONITORING: Count messages processed from Kafka
                    processing_counters.device_processed += 1
            except asyncio.QueueFull:
                # If chunk fails, try individual messages
                dropped_count = 0
                for message in chunk:
                    try:
                        device_queues[device_id].put_nowait(message)
                        processing_counters.device_processed += 1
                    except asyncio.QueueFull:
                        dropped_count += 1

                if dropped_count > 0:
                    logger.warning(
                        f"⚠️ [{device_id}] Broadcast queue full, dropped {dropped_count} messages from chunk"
                    )
                    # ✅ Explicit queue overflow tracking with metrics
                    try:
                        from app.metrics import BROADCAST_QUEUE_DROPPED

                        BROADCAST_QUEUE_DROPPED.labels(device_id=device_id).inc(
                            dropped_count
                        )
                    except ImportError:
                        pass  # Metrics not available

        # Save messages if per-device save flag is enabled
        # Check save mode from shared_state (set via WebSocket "save" message)
        if app.shared_state.is_save_enabled(device_id):
            await start_device_saver(device_id)
            for i, message in enumerate(batch_data):
                try:
                    if device_id not in device_save_queues:
                        from app.message_processor import MAX_SAVE_QUEUE_SIZE

                        device_save_queues[device_id] = asyncio.Queue(
                            maxsize=MAX_SAVE_QUEUE_SIZE
                        )
                    device_save_queues[device_id].put_nowait(message)
                except asyncio.QueueFull:
                    dropped = len(batch_data) - i
                    logger.warning(
                        f"⚠️ [{device_id}] Save queue full, dropped {dropped} messages"
                    )
                    # ✅ Explicit queue overflow tracking with metrics
                    try:
                        from app.metrics import SAVE_QUEUE_DROPPED

                        SAVE_QUEUE_DROPPED.labels(device_id=device_id).inc(dropped)
                    except ImportError:
                        pass  # Metrics not available
                    break

        logger.info(
            f"✅ Processed {len(batch_data)} messages from Kafka for device {device_id}"
        )

    except Exception as e:
        logger.error(f"❌ Error processing Kafka batch for device {device_id}: {e}")


async def start_kafka_consumer_for_device(device_id: str, message_handler):
    """Start a Kafka consumer for a specific device with supervision."""
    try:
        from app.kafka_client import start_kafka_consumer_for_device as start_consumer

        # Use the helper function from kafka_client
        await start_consumer(device_id, message_handler)

        # Initialize health stats
        consumer_health_stats[device_id] = {
            "status": "running",
            "started_at": time.time(),
            "restart_attempts": 0,
        }

        logger.info(f"✅ Started supervised Kafka consumer for device {device_id}")

    except Exception as e:
        logger.error(f"❌ Failed to start Kafka consumer for device {device_id}: {e}")
        active_kafka_consumers[device_id] = False
        consumer_health_stats[device_id] = {
            "status": "failed",
            "last_failure": time.time(),
            "last_exception": str(e),
            "restart_attempts": consumer_health_stats.get(device_id, {}).get(
                "restart_attempts", 0
            )
            + 1,
        }
        raise


async def start_kafka_consumers_for_known_devices():
    """
    Start Kafka consumers for all configured devices.
    Uses fixed topic configuration for simplified setup.
    """
    # ✅ FIXED DEVICE LIST: Only use configured devices
    known_devices = get_all_device_ids()

    logger.info(f"🚀 Starting Kafka consumers for {len(known_devices)} known devices")

    for device_id in known_devices:
        if device_id not in active_kafka_consumers:
            try:
                await start_kafka_consumer_for_device(device_id, kafka_message_handler)
                active_kafka_consumers[device_id] = True
                logger.info(f"✅ Started Kafka consumer for device {device_id}")
            except Exception as e:
                logger.error(
                    f"❌ Failed to start Kafka consumer for device {device_id}: {e}"
                )
                active_kafka_consumers[device_id] = False


async def dynamic_kafka_consumer_manager():
    """
    Dynamically manage Kafka consumers based on discovered devices.
    Monitors device_config and starts consumers for new devices.
    """
    logger.info("🔄 Starting dynamic Kafka consumer manager")

    while True:
        try:
            # Check for new devices in device_config
            # ✅ Fix mutating dict iteration - create snapshot first
            for device_id in list(device_config.keys()):
                if device_id not in active_kafka_consumers:
                    try:
                        logger.info(
                            f"🆕 Discovered new device {device_id}, starting Kafka consumer"
                        )
                        await start_kafka_consumer_for_device(
                            device_id, kafka_message_handler
                        )
                        active_kafka_consumers[device_id] = True
                        logger.info(
                            f"✅ Started Kafka consumer for new device {device_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"❌ Failed to start Kafka consumer for device {device_id}: {e}"
                        )
                        active_kafka_consumers[device_id] = False

            # Sleep before checking again
            await asyncio.sleep(30)  # Check every 30 seconds

        except Exception as e:
            logger.error(f"❌ Error in dynamic Kafka consumer manager: {e}")
            await asyncio.sleep(10)


async def kafka_consumer_health_monitor():
    """
    Monitor the health of Kafka consumers and restart if needed.
    """
    logger.info("🏥 Starting Kafka consumer health monitor")

    while True:
        try:
            # Get Kafka statistics
            kafka_stats = get_kafka_stats()

            # Log Kafka consumer status
            active_consumers = sum(
                1 for status in active_kafka_consumers.values() if status
            )
            total_consumers = len(active_kafka_consumers)

            logger.info(
                f"📊 Kafka Health: {active_consumers}/{total_consumers} consumers active"
            )
            logger.info(
                f"📊 Kafka Stats: {kafka_stats.get('frames_consumed', 0)} frames consumed, "
                f"{kafka_stats.get('data_points_consumed', 0)} data points consumed"
            )

            # Check for failed consumers and attempt restart
            failed_consumers = [
                device_id
                for device_id, status in active_kafka_consumers.items()
                if not status
            ]
            if failed_consumers:
                logger.warning(
                    f"⚠️ Found {len(failed_consumers)} failed consumers, attempting restart"
                )
                for device_id in failed_consumers:
                    try:
                        await start_kafka_consumer_for_device(
                            device_id, kafka_message_handler
                        )
                        active_kafka_consumers[device_id] = True
                        logger.info(
                            f"🔄 Restarted Kafka consumer for device {device_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"❌ Failed to restart Kafka consumer for device {device_id}: {e}"
                        )

            # Sleep before next health check
            await asyncio.sleep(60)  # Health check every minute

        except Exception as e:
            logger.error(f"❌ Error in Kafka consumer health monitor: {e}")
            await asyncio.sleep(30)


def get_kafka_consumer_stats():
    """Get statistics about Kafka consumers"""
    active_consumers = sum(1 for status in active_kafka_consumers.values() if status)
    total_consumers = len(active_kafka_consumers)

    return {
        "active_kafka_consumers": active_consumers,
        "total_kafka_consumers": total_consumers,
        "kafka_consumer_devices": list(active_kafka_consumers.keys()),
        "failed_consumers": [
            device_id
            for device_id, status in active_kafka_consumers.items()
            if not status
        ],
    }


# Export functions for use in main.py
__all__ = [
    "start_kafka_consumers_for_known_devices",
    "dynamic_kafka_consumer_manager",
    "kafka_consumer_health_monitor",
    "get_kafka_consumer_stats",
    "kafka_message_handler",
]
