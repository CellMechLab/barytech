"""
Kafka-First MQTT Handler - Durable Ingestion Buffer
Sends MQTT messages directly to Kafka for zero data loss
"""

import asyncio
import logging
import os
import time
import zlib
from typing import Optional

import orjson
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from .config.kafka_topics import get_topic_for_device, is_device_configured
from .utils_compress import codec_from_mqtt_props, sniff_codec_from_magic

# Check for zstandard support
try:
    import zstandard as zstd

    HAS_ZSTD = True
except Exception:
    HAS_ZSTD = False

# Configure logging - reduce Kafka debug noise
logging.basicConfig(level=logging.INFO)
logging.getLogger("aiokafka").setLevel(logging.WARNING)
logging.getLogger("aiokafka.producer").setLevel(logging.WARNING)
logging.getLogger("aiokafka.conn").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def decode_payload_from_mqtt(payload, props=None):
    """
    Decode MQTT payload that may be compressed with zstd/zlib and prefixed
    with a magic header. Returns parsed JSON (dict or list).
    """
    # Normalize to bytes
    if isinstance(payload, str):
        payload_bytes = payload.encode("utf-8", errors="strict")
    else:
        payload_bytes = bytes(payload)

    # 1) Detect codec from magic header (ZSTD\0 / ZLIB\0)
    magic_codec = sniff_codec_from_magic(payload_bytes)

    # Strip magic header if present (magic header takes precedence)
    if magic_codec == "zstd" and payload_bytes.startswith(b"ZSTD\0"):
        body = payload_bytes[5:]  # Strip 5-byte magic header
        codec = "zstd"
    elif magic_codec == "zlib" and payload_bytes.startswith(b"ZLIB\0"):
        body = payload_bytes[5:]  # Strip 5-byte magic header
        codec = "zlib"
    else:
        # No magic header, check MQTT properties
        body = payload_bytes
        # 2) Optionally detect codec from MQTT v5 properties (content-encoding)
        header_codec = None
        if props is not None:
            try:
                header_codec = codec_from_mqtt_props(props)
            except Exception:
                header_codec = None
        codec = header_codec or "none"

    # 3) Decompress if needed
    if codec == "zstd":
        if not HAS_ZSTD:
            raise RuntimeError(
                "Received zstd-compressed payload but zstandard is not installed"
            )
        dctx = zstd.ZstdDecompressor()
        raw = dctx.decompress(body)
    elif codec == "zlib":
        raw = zlib.decompress(body)
    else:
        # "none" or unknown: assume plain JSON bytes
        raw = body

    # 4) Parse JSON
    return orjson.loads(raw)


class KafkaFirstMQTTHandler:
    """MQTT handler that sends messages directly to Kafka for zero data loss"""

    def __init__(self):
        self.kafka_producer: Optional[AIOKafkaProducer] = None
        self.kafka_available = True
        self.kafka_errors = 0
        self.messages_sent = 0
        self.data_points_sent = 0  # Count individual data points inside messages
        # self.fallback_queue = None  # Unused
        self.event_loop = None  # ✅ Store reference to main event loop

        # ✅ Kafka buffering and overflow queue
        self.overflow_queue = asyncio.Queue(
            maxsize=100000
        )  # 100K message overflow buffer
        self.retry_queue = asyncio.Queue(maxsize=50000)  # 50K message retry buffer
        self.max_retries = 3
        self.retry_backoff_ms = 100
        self.request_timeout_ms = 30000

        # Configuration
        self.kafka_enabled = (
            os.environ.get("KAFKA_FIRST_MODE", "false").lower() == "true"
        )
        self.kafka_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.raw_topic = os.environ.get("KAFKA_RAW_TOPIC", "iot_raw_ingestion")

        # Bind helper methods
        self._extract_device_id = self._extract_device_id
        self._parse_device_from_topic = self._parse_device_from_topic

    def _parse_device_from_topic(self, topic: Optional[str]) -> Optional[str]:
        """Extract device_id from MQTT topic like device_data/<deviceId>"""
        if not topic:
            return None
        # e.g., "device_data/frontend1_ultra_high_perf_device"
        parts = topic.split("/")
        return parts[-1] if parts else None

    def _extract_device_id(
        self,
        message,
        device_hint: Optional[str] = None,
        topic_hint: Optional[str] = None,
    ) -> Optional[str]:
        """
        Extract device_id from a JSON-decoded message that can be dict or list.
        Priority: dict.device_id > first_list_item.device_id > device_hint > topic_hint > None
        """
        # dict payload
        if isinstance(message, dict):
            did = message.get("device_id")
            if did:
                return did

        # list (batch) payload
        if isinstance(message, list) and message:
            first = message[0]
            if isinstance(first, dict):
                did = first.get("device_id")
                if did:
                    return did

        # fallbacks
        return device_hint or self._parse_device_from_topic(topic_hint)

    async def start_kafka_producer(self):
        """Initialize Kafka producer for immediate ingestion"""
        # ✅ Store reference to current event loop for thread-safe operations
        self.event_loop = asyncio.get_running_loop()

        if not self.kafka_enabled:
            logger.info("🔧 Kafka-first mode disabled, using direct processing")
            return

        try:
            # ✅ Fixed compatibility with newer aiokafka versions with more patient settings
            self.kafka_producer = AIOKafkaProducer(
                bootstrap_servers=self.kafka_servers,
                compression_type="gzip",  # Reliable compression for stability
                acks=1,  # Fast acknowledgment (not 'all' for speed)
                # More patient settings to prevent send_and_wait from panicking quickly
                request_timeout_ms=30000,  # 30s instead of small default
                linger_ms=50,  # Allow small batching (increased from 5ms)
                max_batch_size=64 * 1024,  # 64KB batch
                max_request_size=1048576,  # 1MB max request
                value_serializer=lambda x: (
                    orjson.dumps(x) if isinstance(x, (dict, list)) else x
                ),  # Serialize dict/list to JSON bytes
            )

            await self.kafka_producer.start()
            self.kafka_available = True
            logger.info(f"✅ Kafka-first producer started: {self.kafka_servers}")

            # ✅ Start background queue processors
            await self.start_queue_processors()

        except Exception as e:
            logger.error(f"❌ Kafka producer startup failed: {e}")
            self.kafka_available = False
            raise

    async def stop_kafka_producer(self):
        """Stop Kafka producer"""
        if self.kafka_producer:
            await self.kafka_producer.stop()
            logger.info("🔌 Kafka-first producer stopped")

    def on_message(self, client, topic, payload, qos, properties):
        """MQTT callback - send to Kafka immediately (gmqtt compatible)"""
        try:
            logger.info(
                f"🔄 Kafka-first handler received message: {len(payload)} bytes from topic={topic}"
            )
            if self.event_loop and not self.event_loop.is_closed():
                # ✅ Schedule coroutine on the main event loop from MQTT thread
                logger.info("📤 Scheduling message for Kafka processing")
                asyncio.run_coroutine_threadsafe(
                    self.handle_message_async(
                        payload, topic=topic, device_hint=None, properties=properties
                    ),
                    self.event_loop,
                )
            else:
                logger.error(
                    "❌ Event loop not available - falling back to sync processing"
                )
                # Fallback: Add to queue for direct processing
                try:
                    # Removed old mqtt_client import - using new async client
                    logger.warning("⚠️ Used fallback queue for message processing")
                except Exception as fallback_error:
                    logger.error(f"❌ Fallback processing failed: {fallback_error}")
        except Exception as e:
            logger.error(f"❌ MQTT callback error: {e}")

    async def handle_message_async(
        self,
        raw_payload: bytes,
        topic: Optional[str] = None,
        device_hint: Optional[str] = None,
        properties=None,
    ):
        """Handle MQTT message with Kafka-first approach"""
        try:
            # Normalize to bytes to send to Kafka as-is
            if isinstance(raw_payload, str):
                raw_payload = raw_payload.encode("utf-8")
            else:
                raw_payload = bytes(raw_payload)

            logger.info(
                f"🔄 Processing message: kafka_available={self.kafka_available}, producer_exists={self.kafka_producer is not None}"
            )
            if self.kafka_available and self.kafka_producer:
                # PRIMARY PATH: Send to Kafka immediately
                logger.info("📤 Sending message to Kafka")
                success = await self.send_to_kafka(
                    raw_payload,
                    topic_hint=topic,
                    device_hint=device_hint,
                    properties=properties,
                )
                if success:
                    self.messages_sent += 1
                    # ✅ Decode only for local stats / logging
                    frames_count = None
                    try:
                        payload_obj = decode_payload_from_mqtt(
                            raw_payload, props=properties
                        )
                        if isinstance(payload_obj, list):
                            frames_count = len(payload_obj)
                        else:
                            frames_count = 1
                    except Exception as e:
                        logger.error(
                            f"❌ Failed to decode payload for stats: {e}",
                            exc_info=True,
                        )
                        payload_obj = None
                        frames_count = 1  # Count as 1 if can't parse

                    if frames_count is not None:
                        self.data_points_sent += frames_count

                    logger.info(
                        f"✅ Message sent to Kafka (total: {self.messages_sent} frames, {self.data_points_sent} data points)"
                    )
                    return
                else:
                    logger.warning("⚠️ Failed to send to Kafka, using fallback")
            else:
                logger.warning(
                    f"⚠️ Kafka not available: kafka_available={self.kafka_available}, producer={self.kafka_producer is not None}"
                )

            # FALLBACK PATH: Direct processing queue
            logger.warning("⚠️ Using direct processing fallback")
            await self.direct_fallback(raw_payload)

        except Exception as e:
            logger.error(f"❌ Message handling error: {e}")
            await self.direct_fallback(raw_payload)

    async def send_to_kafka(
        self,
        raw_payload: bytes,
        *,
        topic_hint: Optional[str] = None,
        device_hint: Optional[str] = None,
        properties=None,
    ) -> bool:
        """Send raw MQTT payload directly to Kafka with retry and overflow handling"""
        try:
            # ✅ Decode payload to figure out device_id and create payload_dict
            # Use decode_payload_from_mqtt to handle compression
            message = None
            try:
                message = decode_payload_from_mqtt(raw_payload, props=properties)
            except Exception as e:
                logger.warning(
                    f"⚠️ Failed to decode payload for device_id extraction: {e}, using hints"
                )
                message = None  # keep going; we can still use topic/device_hint

            device_id = (
                self._extract_device_id(
                    message, device_hint=device_hint, topic_hint=topic_hint
                )
                or "unknown"
            )

            # ✅ FIXED TOPIC MAPPING: Use predefined topics only
            if not is_device_configured(device_id):
                logger.error(
                    f"❌ Device '{device_id}' is not configured for Kafka topics"
                )
                return False

            topic = get_topic_for_device(device_id)

            # Detect compression codec only for logging (we ALWAYS send decompressed JSON to Kafka)
            codec = codec_from_mqtt_props(properties) or sniff_codec_from_magic(
                raw_payload
            )
            if codec:
                logger.debug(
                    f"📦 Original MQTT compression: {codec} for device {device_id}"
                )

            # ⚠️ IMPORTANT:
            # Do NOT include content-encoding in Kafka headers, because the value_serializer
            # already turns the decoded dict/list into plain JSON bytes. If we advertise a
            # codec here, the Kafka consumer will try to decompress already-plain JSON.
            headers = [
                ("source", b"mqtt"),
                ("device_id", device_id.encode()),
                ("ingestion_time", str(time.time()).encode()),
                ("handler", b"kafka_first"),
                (
                    "msg_type",
                    (
                        b"list"
                        if isinstance(message, list)
                        else b"dict" if isinstance(message, dict) else b"bytes"
                    ),
                ),
            ]

            # ✅ Prepare payload_dict for Kafka (decoded JSON object)
            payload_dict = message
            if payload_dict is None:
                # Fallback: try to decode again, or fail
                try:
                    payload_dict = decode_payload_from_mqtt(
                        raw_payload, props=properties
                    )
                except Exception as e:
                    logger.error(
                        f"❌ Failed to decode payload to dict for device {device_id}: {e}"
                    )
                    return False

            for attempt in range(self.max_retries):
                try:
                    # Send with device_id as key for consistent partitioning
                    # ✅ Pass dict/list to value_serializer (it will JSON-encode)
                    await self.kafka_producer.send_and_wait(
                        topic=topic,
                        key=device_id.encode(),
                        value=payload_dict,
                        headers=headers,
                    )

                    logger.info(
                        f"✅ Kafka ingestion -> topic={topic}, device={device_id}"
                    )
                    return True

                except KafkaError as e:
                    if attempt < self.max_retries - 1:
                        logger.warning(
                            f"⚠️ Kafka send attempt {attempt + 1} failed: {e}, retrying..."
                        )
                        await asyncio.sleep(
                            self.retry_backoff_ms / 1000
                        )  # Convert ms to seconds
                        continue
                    else:
                        # Final attempt failed, add to retry queue
                        logger.error(
                            f"❌ Kafka send failed after {self.max_retries} attempts: {e}"
                        )
                        await self.add_to_retry_queue(raw_payload, device_id)
                        return False

        except Exception as e:
            logger.error(f"❌ Unexpected error in Kafka send: {e}")
            # Add to overflow queue as fallback
            await self.add_to_overflow_queue(raw_payload)
            return False

    async def add_to_retry_queue(self, raw_payload: bytes, device_id: str):
        """Add failed message to retry queue"""
        try:
            if self.retry_queue.qsize() < self.retry_queue.maxsize:
                await self.retry_queue.put(
                    {
                        "payload": raw_payload,
                        "device_id": device_id,
                        "retry_count": 0,
                        "timestamp": time.time(),
                    }
                )
                logger.info(
                    f"📥 Added to retry queue: {device_id} (size: {self.retry_queue.qsize()})"
                )
            else:
                logger.warning(f"⚠️ Retry queue full, adding to overflow: {device_id}")
                await self.add_to_overflow_queue(raw_payload)
        except Exception as e:
            logger.error(f"❌ Error adding to retry queue: {e}")
            await self.add_to_overflow_queue(raw_payload)

    async def add_to_overflow_queue(self, raw_payload: bytes):
        """Add message to overflow queue when all else fails"""
        try:
            if self.overflow_queue.qsize() < self.overflow_queue.maxsize:
                await self.overflow_queue.put(
                    {
                        "payload": raw_payload,
                        "timestamp": time.time(),
                        "source": "kafka_failure",
                    }
                )
                logger.info(
                    f"📥 Added to overflow queue (size: {self.overflow_queue.qsize()})"
                )

                # Update Prometheus metrics
                try:
                    from app.metrics import OVERFLOW_QUEUE_SIZE

                    OVERFLOW_QUEUE_SIZE.set(self.overflow_queue.qsize())
                except ImportError:
                    pass
            else:
                logger.error("🚨 Overflow queue full - message lost!")
                # Update Prometheus metrics for message loss
                try:
                    from app.metrics import record_message_loss

                    record_message_loss("overflow_queue_full")
                except ImportError:
                    pass
        except Exception as e:
            logger.error(f"❌ Error adding to overflow queue: {e}")

    async def direct_fallback(self, raw_payload: bytes):
        """Fallback to direct processing queue"""
        try:
            # Removed old mqtt_client import - using new async client
            logger.debug("📥 Fallback to direct processing")
            # Note: Fallback queue removed - Kafka-first mode handles all messages

        except Exception as e:
            logger.error(f"❌ Fallback processing failed: {e}")

    def get_stats(self) -> dict:
        """Get Kafka-first handler statistics"""
        return {
            "kafka_enabled": self.kafka_enabled,
            "kafka_available": self.kafka_available,
            "mqtt_frames_sent_to_kafka": self.messages_sent,  # MQTT frames sent to Kafka
            "data_points_sent_to_kafka": self.data_points_sent,  # Individual data points sent
            "kafka_errors": self.kafka_errors,
            "error_rate": self.kafka_errors / max(self.messages_sent, 1),
            "avg_data_points_per_frame": self.data_points_sent
            / max(self.messages_sent, 1),
            # ✅ Queue monitoring
            "retry_queue_size": self.retry_queue.qsize(),
            "overflow_queue_size": self.overflow_queue.qsize(),
            "retry_queue_max": self.retry_queue.maxsize,
            "overflow_queue_max": self.overflow_queue.maxsize,
        }

    async def health_check(self) -> dict:
        """Check Kafka producer health"""
        if not self.kafka_enabled:
            return {"status": "disabled", "reason": "KAFKA_FIRST_MODE=false"}

        if not self.kafka_producer:
            return {"status": "not_started", "reason": "Producer not initialized"}

        if not self.kafka_available:
            return {"status": "unavailable", "reason": f"Errors: {self.kafka_errors}"}

        # Try to get metadata as health check
        try:
            metadata = await self.kafka_producer.client.fetch_all_metadata()
            # Handle both method and attribute access for metadata.topics
            topics = metadata.topics() if callable(metadata.topics) else metadata.topics

            if self.raw_topic in topics:
                partition_count = len(topics[self.raw_topic].partitions)
                return {
                    "status": "healthy",
                    "topic": self.raw_topic,
                    "partitions": partition_count,
                    "messages_sent": self.messages_sent,
                    "error_rate": self.kafka_errors / max(self.messages_sent, 1),
                }
            else:
                return {"status": "topic_missing", "topic": self.raw_topic}

        except Exception as e:
            return {"status": "health_check_failed", "error": str(e)}

    async def process_retry_queue(self):
        """Process messages in retry queue with exponential backoff"""
        while not self.retry_queue.empty():
            try:
                retry_item = await self.retry_queue.get()
                payload = retry_item["payload"]
                device_id = retry_item["device_id"]
                retry_count = retry_item["retry_count"]

                if retry_count < self.max_retries:
                    # Exponential backoff
                    backoff_time = (self.retry_backoff_ms * (2**retry_count)) / 1000
                    await asyncio.sleep(backoff_time)

                    # Try to send again
                    success = await self.send_to_kafka(
                        payload, topic_hint=None, device_hint=device_id
                    )
                    if not success:
                        # Increment retry count and put back if not at max
                        retry_item["retry_count"] += 1
                        if retry_item["retry_count"] < self.max_retries:
                            await self.retry_queue.put(retry_item)
                        else:
                            # Max retries reached, move to overflow
                            logger.warning(
                                f"🚨 Max retries reached for {device_id}, moving to overflow"
                            )
                            await self.add_to_overflow_queue(payload)
                else:
                    # Max retries reached, move to overflow
                    await self.add_to_overflow_queue(payload)

            except Exception as e:
                logger.error(f"❌ Error processing retry queue: {e}")
                await asyncio.sleep(1)  # Brief pause on error

    async def process_overflow_queue(self):
        """Process messages in overflow queue (persistent storage fallback)"""
        while not self.overflow_queue.empty():
            try:
                overflow_item = await self.overflow_queue.get()
                payload = overflow_item["payload"]

                # Try to send to Kafka one more time
                success = await self.send_to_kafka(
                    payload, topic_hint=None, device_hint=None
                )
                if not success:
                    # TODO: Implement persistent file storage fallback
                    # For now, log the overflow message
                    logger.warning(
                        f"📝 Overflow message not processed: {len(payload)} bytes"
                    )

            except Exception as e:
                logger.error(f"❌ Error processing overflow queue: {e}")
                await asyncio.sleep(1)  # Brief pause on error

    async def start_queue_processors(self):
        """Start background tasks for processing retry and overflow queues"""
        asyncio.create_task(self._retry_queue_processor())
        asyncio.create_task(self._overflow_queue_processor())
        logger.info("🚀 Started retry and overflow queue processors")

    async def _retry_queue_processor(self):
        """Background task for processing retry queue"""
        while True:
            try:
                await self.process_retry_queue()
                await asyncio.sleep(1)  # Check every second
            except Exception as e:
                logger.error(f"❌ Retry queue processor error: {e}")
                await asyncio.sleep(5)  # Longer pause on error

    async def _overflow_queue_processor(self):
        """Background task for processing overflow queue"""
        while True:
            try:
                await self.process_overflow_queue()
                await asyncio.sleep(5)  # Check every 5 seconds
            except Exception as e:
                logger.error(f"❌ Overflow queue processor error: {e}")
                await asyncio.sleep(10)  # Longer pause on error


# Global instance
kafka_first_handler = KafkaFirstMQTTHandler()


# Integration functions for existing MQTT client
async def start_kafka_first_handler():
    """Start the Kafka-first handler"""
    # Set the event loop for the handler
    kafka_first_handler.event_loop = asyncio.get_running_loop()
    # Enable Kafka-first mode from environment
    kafka_first_handler.kafka_enabled = (
        os.environ.get("KAFKA_FIRST_MODE", "true").lower() == "true"
    )
    print(f"🔧 Kafka-first mode: {kafka_first_handler.kafka_enabled}")
    print(f"🔧 Kafka servers: {kafka_first_handler.kafka_servers}")
    print(f"🔧 Raw topic: {kafka_first_handler.raw_topic}")
    print(
        "🔧 Topic strategy: Fixed topics (iot-device-frontend1_ultra_high_perf_device, iot-device-frontend2_ultra_high_perf_device)"
    )
    # Set Kafka servers from environment
    kafka_first_handler.kafka_servers = os.environ.get(
        "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
    )
    # Set raw topic from environment (default to "auto" for per-device topics)
    kafka_first_handler.raw_topic = os.environ.get("KAFKA_RAW_TOPIC", "auto")
    print(f"🔧 Final config - Kafka enabled: {kafka_first_handler.kafka_enabled}")
    await kafka_first_handler.start_kafka_producer()
    # Start queue processors for retry and overflow handling
    await kafka_first_handler.start_queue_processors()


async def stop_kafka_first_handler():
    """Stop the Kafka-first handler"""
    await kafka_first_handler.stop_kafka_producer()


def get_kafka_first_stats():
    """Get Kafka-first statistics"""
    return kafka_first_handler.get_stats()


async def get_kafka_first_health():
    """Get Kafka-first health status"""
    return await kafka_first_handler.health_check()


# MQTT callback for Kafka-first processing (gmqtt compatible)
async def on_message_kafka_first(client, topic, payload, qos, properties):
    """MQTT callback that sends directly to Kafka - gmqtt compatible signature"""
    print(f"📤 Kafka-first handler: Processing message from topic={topic}")
    print(f"   📦 Payload length: {len(payload)} bytes")
    print(f"   📦 Payload preview: {payload[:100] if payload else 'None'}")
    await kafka_first_handler.handle_message_async(
        payload, topic=topic, properties=properties
    )
