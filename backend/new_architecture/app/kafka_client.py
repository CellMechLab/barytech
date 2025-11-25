"""
Kafka Client for Ultra-High Performance IoT Data Processing
Handles MQTT to Kafka bridging and Kafka consumption for device processing
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError

from .config.kafka_topics import (
    get_all_topics,
    get_topic_for_device,
    is_device_configured,
)
from .utils_compress import safe_json_loads, sniff_codec_from_magic

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KafkaConfig:
    """Kafka configuration settings"""

    BOOTSTRAP_SERVERS = "localhost:9092"
    COMPRESSION_TYPE = "gzip"  # Reliable compression for stability
    ACKS = 1  # Balance between speed and durability (vs QoS 0)
    # RETRIES = 3  # Unused
    # MAX_IN_FLIGHT_REQUESTS = 5  # Unused
    BATCH_SIZE = 32768  # 32KB batches
    LINGER_MS = 10  # Wait 10ms for batching
    # BUFFER_MEMORY removed - Java-only setting, ignored by aiokafka

    # Message size limits
    MAX_REQUEST_SIZE = 1048576  # 1MB max request size
    # MAX_MESSAGE_BYTES = 1048576  # Unused
    # FETCH_MAX_BYTES = 52428800  # Unused
    # MAX_PARTITION_FETCH_BYTES = 1048576  # Unused

    # Consumer settings
    # GROUP_ID = "iot-processing-group"  # Unused - using per-device group IDs instead
    AUTO_OFFSET_RESET = "earliest"  # Read from beginning to avoid missing messages
    # ENABLE_AUTO_COMMIT = True  # Unused - using manual commits
    # AUTO_COMMIT_INTERVAL_MS = 1000  # Unused - using manual commits
    # Removed MAX_POLL_RECORDS - not supported by aiokafka
    GETMANY_TIMEOUT_MS = 20  # Lower timeout for better latency
    GETMANY_MAX_RECORDS = 2000  # Max records per getmany() call


class KafkaMetrics:
    """Kafka performance metrics"""

    def __init__(self):
        self.frames_produced = 0  # Kafka messages (frames) produced
        self.data_points_produced = 0  # Individual data points produced
        self.frames_consumed = 0  # Kafka messages (frames) consumed
        self.data_points_consumed = 0  # Individual data points consumed
        self.production_errors = 0
        self.consumption_errors = 0
        self.start_time = time.time()

    def get_stats(self):
        elapsed = time.time() - self.start_time
        return {
            "frames_produced": self.frames_produced,
            "data_points_produced": self.data_points_produced,
            "frames_consumed": self.frames_consumed,
            "data_points_consumed": self.data_points_consumed,
            "production_errors": self.production_errors,
            "consumption_errors": self.consumption_errors,
            "elapsed_time": elapsed,
            "frame_production_rate": (
                self.frames_produced / elapsed if elapsed > 0 else 0
            ),
            "data_point_production_rate": (
                self.data_points_produced / elapsed if elapsed > 0 else 0
            ),
            "frame_consumption_rate": (
                self.frames_consumed / elapsed if elapsed > 0 else 0
            ),
            "data_point_consumption_rate": (
                self.data_points_consumed / elapsed if elapsed > 0 else 0
            ),
            "avg_data_points_per_frame_produced": self.data_points_produced
            / max(self.frames_produced, 1),
            "avg_data_points_per_frame_consumed": self.data_points_consumed
            / max(self.frames_consumed, 1),
        }


# Global metrics instance
kafka_metrics = KafkaMetrics()


class KafkaProducerManager:
    """Manages Kafka producer with connection pooling and error handling"""

    def __init__(self):
        self.producer: Optional[AIOKafkaProducer] = None
        self.is_connected = False

    async def start(self):
        """Start the Kafka producer"""
        try:
            logger.info(
                f"🟡 Attempting to start Kafka producer at {KafkaConfig.BOOTSTRAP_SERVERS}"
            )
            logger.info(
                f"   Configuration: compression={KafkaConfig.COMPRESSION_TYPE}, acks={KafkaConfig.ACKS}, linger_ms={KafkaConfig.LINGER_MS}"
            )

            # ✅ Fixed compatibility with newer aiokafka versions with more patient settings
            self.producer = AIOKafkaProducer(
                bootstrap_servers=KafkaConfig.BOOTSTRAP_SERVERS,
                compression_type=KafkaConfig.COMPRESSION_TYPE,
                acks=KafkaConfig.ACKS,
                # More patient settings to prevent send_and_wait from panicking quickly
                request_timeout_ms=30000,  # 30s instead of small default
                linger_ms=50,  # Allow small batching (increased from 10ms)
                max_batch_size=64 * 1024,  # 64KB batch
                max_request_size=KafkaConfig.MAX_REQUEST_SIZE,
                value_serializer=lambda x: x,  # We'll serialize manually with orjson
            )

            logger.info("🔄 AIOKafkaProducer instance created, attempting to start...")
            await self.producer.start()
            self.is_connected = True
            logger.info("✅ Kafka producer started successfully")

        except Exception:
            logger.exception("❌ Kafka producer failed to start")
            self.is_connected = False
            raise

    async def stop(self):
        """Stop the Kafka producer"""
        if self.producer:
            await self.producer.stop()
            self.is_connected = False
            logger.info("🔌 Kafka producer stopped")

    async def send_batch(self, device_id: str, batch_data: List[dict]) -> bool:
        """Send a batch of messages to Kafka topic"""
        if not self.is_connected or not self.producer:
            logger.error("❌ Kafka producer not connected")
            return False

        try:
            # ✅ FIXED TOPIC MAPPING: Use predefined topics only
            if not is_device_configured(device_id):
                logger.error(
                    f"❌ Device '{device_id}' is not configured for Kafka topics"
                )
                return False

            topic = get_topic_for_device(device_id)

            # Serialize batch with orjson for speed
            payload = orjson.dumps(batch_data)

            # Send to Kafka with device_id as partition key for ordering
            await self.producer.send_and_wait(
                topic=topic,
                value=payload,
                key=device_id.encode("utf-8"),  # Partition by device for ordering
            )

            kafka_metrics.frames_produced += 1  # Count Kafka message (frame)
            kafka_metrics.data_points_produced += len(
                batch_data
            )  # Count individual data points
            # ✅ Add logging to prove per-device producer is firing
            logger.info(
                f"📤 per-device produce -> topic={topic}, frame=1, data_points={len(batch_data)}"
            )
            logger.debug(
                f"📤 Sent batch of {len(batch_data)} messages to Kafka topic {topic}"
            )
            return True

        except KafkaError as e:
            kafka_metrics.production_errors += 1
            logger.error(f"❌ Kafka send error for device {device_id}: {e}")
            return False
        except Exception as e:
            kafka_metrics.production_errors += 1
            logger.error(f"❌ Unexpected error sending to Kafka: {e}")
            return False


# Global producer instance
kafka_producer = KafkaProducerManager()


class KafkaConsumerManager:
    """Manages Kafka consumers for device-specific processing"""

    def __init__(self, device_id: str, message_handler):
        self.device_id = device_id
        self.message_handler = message_handler
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.is_running = False

        # ✅ FIXED TOPIC MAPPING: Use predefined topics only
        if not is_device_configured(device_id):
            raise ValueError(f"Device '{device_id}' is not configured for Kafka topics")
        self.topic = get_topic_for_device(device_id)

    async def start_consuming(self):
        """Start consuming messages from Kafka topic"""
        try:
            self.consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=KafkaConfig.BOOTSTRAP_SERVERS,
                group_id=f"iot-device-{self.device_id}",  # Unique group ID per device
                auto_offset_reset=KafkaConfig.AUTO_OFFSET_RESET,
                enable_auto_commit=False,  # ✅ Manual commits for reliability - commit only after successful processing
                # ✅ Consumer stability settings to reduce churn and prevent rebalancing
                session_timeout_ms=45000,  # Longer session prevents "member not recognized" during brief event-loop stalls
                heartbeat_interval_ms=15000,  # Longer heartbeat interval (should be < 1/3 of session_timeout_ms)
                max_poll_interval_ms=300000,  # 5 minutes - avoid Kafka thinking consumer is stuck during batching/decompression
                request_timeout_ms=60000,  # 60s timeout for requests to avoid premature failures
                value_deserializer=lambda x: x,  # We'll deserialize manually with orjson
            )

            await self.consumer.start()
            self.is_running = True
            logger.info(
                f"✅ Kafka consumer started for device {self.device_id} on topic {self.topic}"
            )

            # Start consuming loop
            await self._consume_loop()

        except Exception as e:
            logger.error(
                f"❌ Failed to start Kafka consumer for device {self.device_id}: {e}"
            )
            raise

    async def _consume_loop(self):
        """Main consumption loop using getmany() for efficient batching"""
        # Back-pressure configuration
        QUEUE_HIGH_WATERMARK = 80_000
        QUEUE_LOW_WATERMARK = 20_000

        # Manual commit configuration
        COMMIT_EVERY_N_MESSAGES = 1000  # Commit after processing every 1000 messages
        messages_since_commit = 0

        def _total_save_queue_depth():
            """
            Only count queues for devices that actually have save enabled.
            This ensures pure streaming devices never cause Kafka backpressure.
            """
            import app.shared_state
            from app.message_processor import device_save_queues

            total = 0
            for device_id, q in device_save_queues.items():
                # Only count queue depth if save is enabled for this device
                if not app.shared_state.is_save_enabled(device_id):
                    continue
                total += q.qsize()
            return total

        async def apply_backpressure(consumer):
            """Pause/resume Kafka consumption based on queue depth"""
            depth = _total_save_queue_depth()
            if depth > QUEUE_HIGH_WATERMARK:
                # Pause all assigned partitions
                parts = consumer.assignment()
                if parts:
                    consumer.pause(*parts)
                    logger.warning(
                        f"⏸️  Paused Kafka consumption (queue depth={depth:,})"
                    )
            elif depth < QUEUE_LOW_WATERMARK:
                # Resume paused partitions
                parts = consumer.paused()
                if parts:
                    consumer.resume(*parts)
                    logger.info(f"▶️  Resumed Kafka consumption (queue depth={depth:,})")

        try:
            while self.is_running:
                try:
                    # Apply back-pressure before consuming
                    await apply_backpressure(self.consumer)

                    # Use getmany() to fetch batches of messages efficiently
                    # This is the correct way to batch messages in aiokafka
                    msgs_map = await self.consumer.getmany(
                        timeout_ms=KafkaConfig.GETMANY_TIMEOUT_MS,
                        max_records=KafkaConfig.GETMANY_MAX_RECORDS,
                    )

                    if not msgs_map:
                        # No messages received in timeout period
                        await asyncio.sleep(0.01)  # Brief pause to prevent busy waiting
                        continue

                    # Process messages from all topic partitions
                    total_messages_processed = 0

                    for topic_partition, messages in msgs_map.items():
                        logger.debug(
                            f"📥 Processing {len(messages)} messages from {topic_partition}"
                        )

                        # Process each Kafka message individually to correctly count data points
                        # Each Kafka message (frame) contains a compressed batch of ~1000 data points
                        for msg in messages:
                            try:
                                # Extract compression info from headers
                                headers_dict = dict(msg.headers) if msg.headers else {}
                                codec = (
                                    headers_dict.get("content-encoding", b"").decode()
                                    if isinstance(
                                        headers_dict.get("content-encoding"), bytes
                                    )
                                    else headers_dict.get("content-encoding")
                                )

                                # Handle compressed data - decompress to get batch_data
                                if codec or sniff_codec_from_magic(msg.value):
                                    batch_data = safe_json_loads(msg.value, codec)
                                else:
                                    batch_data = orjson.loads(msg.value)

                                # Ensure batch_data is a list for the handler
                                # Handler expects a list of records/data points
                                if not isinstance(batch_data, list):
                                    batch_data = [batch_data]

                                # Let the processor handle the decoded batch
                                await self.message_handler(self.device_id, batch_data)

                                # ✅ Correct counting - count actual data points, not frames
                                message_count = len(
                                    batch_data
                                )  # Number of data points in the decoded batch
                                kafka_metrics.frames_consumed += (
                                    1  # 1 Kafka frame (this message)
                                )
                                kafka_metrics.data_points_consumed += message_count  # N data points (in the decoded batch)
                                total_messages_processed += message_count

                            except Exception as e:
                                kafka_metrics.consumption_errors += 1
                                logger.error(
                                    f"❌ Error processing message for device {self.device_id}: {e}"
                                )

                    if total_messages_processed > 0:
                        logger.debug(
                            f"📊 Processed {total_messages_processed} total messages from Kafka topic {self.topic}"
                        )

                        # ✅ Manual commit after successful processing
                        messages_since_commit += total_messages_processed
                        if messages_since_commit >= COMMIT_EVERY_N_MESSAGES:
                            try:
                                await self.consumer.commit()
                                logger.debug(
                                    f"✅ Committed offsets after processing {messages_since_commit} messages"
                                )
                                messages_since_commit = 0
                            except Exception as commit_error:
                                logger.error(
                                    f"❌ Failed to commit offsets: {commit_error}"
                                )
                                # Don't reset counter - will retry on next batch

                    # Cooperative yield to keep HTTP/WebSocket responsive
                    await asyncio.sleep(0)

                except Exception as e:
                    kafka_metrics.consumption_errors += 1
                    logger.error(
                        f"❌ Error in getmany() loop for device {self.device_id}: {e}"
                    )
                    await asyncio.sleep(1)  # Wait before retrying on error

        except Exception as e:
            logger.error(
                f"❌ Kafka consumer loop error for device {self.device_id}: {e}"
            )
        finally:
            # ✅ Final commit on shutdown to ensure no message loss
            if self.consumer and messages_since_commit > 0:
                try:
                    await self.consumer.commit()
                    logger.info(
                        f"✅ Final commit: {messages_since_commit} messages on shutdown"
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to commit on shutdown: {e}")
            await self.stop()

    async def stop(self):
        """Stop the Kafka consumer"""
        if self.consumer:
            self.is_running = False
            try:
                # ✅ Final commit before stopping
                await self.consumer.commit()
                logger.info("✅ Final offset commit before consumer stop")
            except Exception as e:
                logger.error(f"❌ Failed final commit: {e}")
            await self.consumer.stop()
            logger.info(f"🔌 Kafka consumer stopped for device {self.device_id}")


# Global consumer registry
kafka_consumers: Dict[str, KafkaConsumerManager] = {}


async def start_kafka_producer():
    """Start the global Kafka producer"""
    await kafka_producer.start()


async def stop_kafka_producer():
    """Stop the global Kafka producer"""
    await kafka_producer.stop()


async def forward_to_kafka(device_id: str, batch_data: List[dict]) -> bool:
    """Forward a batch of messages from MQTT to Kafka"""
    return await kafka_producer.send_batch(device_id, batch_data)


async def start_kafka_consumer_for_device(device_id: str, message_handler):
    """Start a Kafka consumer for a specific device"""
    if device_id not in kafka_consumers:
        consumer = KafkaConsumerManager(device_id, message_handler)
        kafka_consumers[device_id] = consumer

        # Start consumer in background task
        asyncio.create_task(consumer.start_consuming())
        logger.info(f"🚀 Started Kafka consumer for device {device_id}")
    else:
        logger.info(f"ℹ️ Kafka consumer for device {device_id} already running")


async def stop_kafka_consumer_for_device(device_id: str):
    """Stop a Kafka consumer for a specific device"""
    if device_id in kafka_consumers:
        await kafka_consumers[device_id].stop()
        del kafka_consumers[device_id]
        logger.info(f"🛑 Stopped Kafka consumer for device {device_id}")


def get_kafka_stats():
    """Get current Kafka performance statistics"""
    stats = kafka_metrics.get_stats()

    # Include Kafka-first stats for complete visibility
    try:
        from app.mqtt_kafka_first import get_kafka_first_stats

        kafka_first_stats = get_kafka_first_stats()
        stats.update(
            {
                "kafka_first_frames_sent": kafka_first_stats.get(
                    "mqtt_frames_sent_to_kafka", 0
                ),
                "kafka_first_data_points_sent": kafka_first_stats.get(
                    "data_points_sent_to_kafka", 0
                ),
                "kafka_first_errors": kafka_first_stats.get("kafka_errors", 0),
                "total_frames_produced": stats["frames_produced"]
                + kafka_first_stats.get("mqtt_frames_sent_to_kafka", 0),
                "total_data_points_produced": stats["data_points_produced"]
                + kafka_first_stats.get("data_points_sent_to_kafka", 0),
                "total_frame_production_rate": (
                    stats["frames_produced"]
                    + kafka_first_stats.get("mqtt_frames_sent_to_kafka", 0)
                )
                / max(stats["elapsed_time"], 1),
                "total_data_point_production_rate": (
                    stats["data_points_produced"]
                    + kafka_first_stats.get("data_points_sent_to_kafka", 0)
                )
                / max(stats["elapsed_time"], 1),
            }
        )

        # Add production balance indicators
        kafka_first_frames = kafka_first_stats.get("mqtt_frames_sent_to_kafka", 0)
        per_device_frames = stats["frames_produced"]

        if kafka_first_frames > 0 and per_device_frames == 0:
            stats["production_mode"] = "kafka_first_only"
        elif per_device_frames > 0 and kafka_first_frames == 0:
            stats["production_mode"] = "per_device_only"
        elif kafka_first_frames > 0 and per_device_frames > 0:
            stats["production_mode"] = "both_active"
        else:
            stats["production_mode"] = "no_producers"

    except Exception:
        stats.update(
            {
                "kafka_first_frames_sent": 0,
                "kafka_first_data_points_sent": 0,
                "kafka_first_errors": 0,
                "total_frames_produced": stats["frames_produced"],
                "total_data_points_produced": stats["data_points_produced"],
                "production_mode": "unknown",
            }
        )

    return stats


def print_kafka_stats():
    """Print current Kafka performance statistics"""
    stats = kafka_metrics.get_stats()

    # Get Kafka-first stats for combined visibility
    kafka_first_stats = None
    try:
        from app.mqtt_kafka_first import get_kafka_first_stats

        kafka_first_stats = get_kafka_first_stats()
    except Exception:
        kafka_first_stats = None

    logger.info("\n📊 KAFKA STATS:")

    # Show frame-level stats (Kafka messages)
    # ✅ FIX: Calculate totals locally to avoid stats.get() fallback issues
    kafka_first_frames = (
        kafka_first_stats.get("mqtt_frames_sent_to_kafka", 0)
        if kafka_first_stats
        else 0
    )
    kafka_first_data_points = (
        kafka_first_stats.get("data_points_sent_to_kafka", 0)
        if kafka_first_stats
        else 0
    )

    total_frames_produced = stats["frames_produced"] + kafka_first_frames
    total_data_points_produced = stats["data_points_produced"] + kafka_first_data_points

    total_frame_rate = stats.get("total_frame_production_rate", 0)
    total_data_point_rate = stats.get("total_data_point_production_rate", 0)

    logger.info(
        f"   Frames Produced: {stats['frames_produced']} (per-device) + {kafka_first_frames} (kafka-first) = {total_frames_produced} total ({total_frame_rate:.1f}/sec)"
    )
    logger.info(
        f"   Frames Consumed: {stats['frames_consumed']} ({stats['frame_consumption_rate']:.1f}/sec)"
    )

    # Show data point-level stats (individual items)
    logger.info(
        f"   Data Points Produced: {stats['data_points_produced']} (per-device) + {kafka_first_data_points} (kafka-first) = {total_data_points_produced} total ({total_data_point_rate:.1f}/sec)"
    )
    logger.info(
        f"   Data Points Consumed: {stats['data_points_consumed']} ({stats['data_point_consumption_rate']:.1f}/sec)"
    )

    # Show averages
    # Use the locally calculated totals, not the potentially incorrect stats values

    if total_frames_produced > 0:
        logger.info(
            f"   Avg Data Points/Frame (Total Produced): {total_data_points_produced / total_frames_produced:.1f}"
        )
    else:
        logger.info("   Avg Data Points/Frame (Total Produced): 0.0")

    logger.info(
        f"   Avg Data Points/Frame (Consumed): {stats['avg_data_points_per_frame_consumed']:.1f}"
    )

    logger.info(f"   Production Errors: {stats['production_errors']}")
    logger.info(f"   Consumption Errors: {stats['consumption_errors']}")
    logger.info(f"   Elapsed Time: {stats['elapsed_time']:.1f} seconds")

    # Show Kafka-first specific stats if available
    if kafka_first_stats:
        logger.info(
            f"   Kafka-First: {kafka_first_stats.get('mqtt_frames_sent_to_kafka', 0)} frames, {kafka_first_stats.get('data_points_sent_to_kafka', 0)} data points"
        )
        logger.info(
            f"   Kafka-First Queues: retry={kafka_first_stats.get('retry_queue_size', 0)}, overflow={kafka_first_stats.get('overflow_queue_size', 0)}"
        )

        # Show production balance using the locally calculated totals
        if total_frames_produced > 0:
            if kafka_first_frames > 0 and stats["frames_produced"] == 0:
                logger.info(
                    "   📊 Production Mode: Kafka-First only (per-device producer disabled)"
                )
            elif stats["frames_produced"] > 0 and kafka_first_frames == 0:
                logger.info(
                    "   📊 Production Mode: Per-Device only (kafka-first handler disabled)"
                )
            elif kafka_first_frames > 0 and stats["frames_produced"] > 0:
                logger.info("   ⚠️ Production Mode: Both active (duplication possible)")
        else:
            logger.info("   📊 Production Mode: No active producers")


# Health check function
async def kafka_health_check() -> Dict[str, any]:
    """Check Kafka connectivity and health"""
    # Check if Kafka is healthy based on connections, not message activity
    producer_healthy = kafka_producer.is_connected
    consumers_healthy = (
        len(kafka_consumers) > 0
    )  # At least one consumer should be running
    topics_available = (
        len(set(f"iot_device_{device_id}" for device_id in kafka_consumers.keys())) > 0
    )

    # Kafka is healthy if all core components are connected
    overall_healthy = producer_healthy and consumers_healthy and topics_available

    health_status = {
        "status": "healthy" if overall_healthy else "unhealthy",
        "producer_connected": producer_healthy,
        "active_consumers": len(kafka_consumers),
        "total_topics": len(get_all_topics()),
        "overall_health": overall_healthy,
    }

    return health_status


__all__ = [
    "start_kafka_producer",
    "stop_kafka_producer",
    "forward_to_kafka",
    "start_kafka_consumer_for_device",
    "stop_kafka_consumer_for_device",
    "get_kafka_stats",
    "print_kafka_stats",
    "kafka_health_check",
]
