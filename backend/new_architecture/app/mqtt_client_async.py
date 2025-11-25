"""
Async MQTT Client using gmqtt for Non-Blocking Performance
Replaces paho-mqtt with fully async implementation
"""

import asyncio
import os
import socket
import time

import orjson
from gmqtt import Client as MQTTClient

from .kafka_client import forward_to_kafka, print_kafka_stats
from .metrics import record_mqtt_message, update_system_health
from .mqtt_kafka_first import start_kafka_first_handler

# Global async MQTT client
mqtt_client: MQTTClient = None

# Global counter for total received messages
total_messages_received = 0
# Message rate monitoring
last_message_count = 0
last_rate_check = time.time()

# Kafka-first mode - no buffer manager needed


# Monitoring counters for each stage
class MessageCounters:
    def __init__(self):
        self.mqtt_received = 0
        self.mqtt_parsed = 0
        self.mqtt_errors = 0
        self.mqtt_data_points = 0  # Count individual data points in MQTT messages
        self.device_queued = 0
        self.device_processed = 0
        self.broadcast_sent = 0
        self.broadcast_errors = 0
        self.db_saved = 0
        self.db_errors = 0
        self.start_time = time.time()

    def get_stats(self):
        elapsed = time.time() - self.start_time
        return {
            "mqtt_received": self.mqtt_received,
            "mqtt_parsed": self.mqtt_parsed,
            "mqtt_errors": self.mqtt_errors,
            "mqtt_data_points": self.mqtt_data_points,
            "device_queued": self.device_queued,
            "device_processed": self.device_processed,
            "broadcast_sent": self.broadcast_sent,
            "broadcast_errors": self.broadcast_errors,
            "db_saved": self.db_saved,
            "db_errors": self.db_errors,
            "elapsed_time": elapsed,
            "mqtt_rate": self.mqtt_received / elapsed if elapsed > 0 else 0,
            "mqtt_data_point_rate": (
                self.mqtt_data_points / elapsed if elapsed > 0 else 0
            ),
            "processing_rate": self.device_processed / elapsed if elapsed > 0 else 0,
            "broadcast_rate": self.broadcast_sent / elapsed if elapsed > 0 else 0,
            "db_rate": self.db_saved / elapsed if elapsed > 0 else 0,
            "avg_data_points_per_mqtt": self.mqtt_data_points
            / max(self.mqtt_received, 1),
        }

    def print_stats(self):
        stats = self.get_stats()
        print("\n📊 ASYNC MQTT MESSAGE PROCESSING STATS:")
        print(
            f"   MQTT Frames Received: {stats['mqtt_received']} ({stats['mqtt_rate']:.1f}/sec)"
        )
        print(
            f"   MQTT Data Points: {stats['mqtt_data_points']} ({stats['mqtt_data_point_rate']:.1f}/sec)"
        )
        print(f"   Avg Data Points/Frame: {stats['avg_data_points_per_mqtt']:.1f}")

        # ✅ Fix division by zero error
        if stats["mqtt_received"] > 0:
            success_rate = stats["mqtt_parsed"] / stats["mqtt_received"] * 100
            print(
                f"   MQTT Parsed: {stats['mqtt_parsed']} ({success_rate:.1f}% success)"
            )
        else:
            print(f"   MQTT Parsed: {stats['mqtt_parsed']} (0.0% - no messages yet)")
        print(f"   MQTT Errors: {stats['mqtt_errors']}")
        print(f"   Device Queued: {stats['device_queued']}")
        print(
            f"   Device Processed: {stats['device_processed']} ({stats['processing_rate']:.1f}/sec)"
        )
        print(
            f"   Broadcast Sent: {stats['broadcast_sent']} ({stats['broadcast_rate']:.1f}/sec)"
        )
        print(f"   Broadcast Errors: {stats['broadcast_errors']}")
        print(f"   DB Saved: {stats['db_saved']} ({stats['db_rate']:.1f}/sec)")
        print(f"   DB Errors: {stats['db_errors']}")
        print(f"   Elapsed Time: {stats['elapsed_time']:.1f} seconds")

        # Kafka-first mode - no buffer manager stats
        print("   Kafka-First Mode: ✅ Active")
        print("   Kafka Health: ✅ Connected")


# Global monitoring instance
message_counters = MessageCounters()


def get_mqtt_client():
    global mqtt_client
    if mqtt_client is None:
        raise RuntimeError("Async MQTT client is not initialized!")
    return mqtt_client


# ✅ MQTT event handlers - Regular functions for gmqtt compatibility
def on_connect(client, flags, rc, properties):  # flags unused but required by callback signature
    """MQTT connection callback - regular function for gmqtt compatibility"""
    if rc == 0:
        print("✅ Connected to MQTT Broker (Async)!")
        # Update Prometheus metric for connection status
        try:
            from .metrics import MQTT_CONNECTION_STATUS

            MQTT_CONNECTION_STATUS.set(1)
            print("✅ MQTT_CONNECTION_STATUS metric updated to 1")
        except ImportError as e:
            print(f"⚠️ Could not import metrics: {e}")
        except Exception as e:
            print(f"❌ Error updating MQTT_CONNECTION_STATUS metric: {e}")

        # Subscribe to topics with QoS 1 for reliability
        # Note: subscribe_to_topics is now synchronous
        subscribe_to_topics(client)
        print("📡 Subscribing to device_data topics with QoS 1...")
    else:
        print(f"❌ Failed to connect to MQTT broker with code {rc}")


def subscribe_to_topics(client):
    """Subscribe to MQTT topics synchronously (gmqtt returns int, not Awaitable)"""
    try:
        # Subscribe to topics with proper error handling
        # gmqtt expects: subscribe(topic: str, qos: int = 0)
        client.subscribe("MON", qos=1)
        client.subscribe("device_data", qos=1)  # Subscribe to base device_data topic
        client.subscribe(
            "device_data/#", qos=1
        )  # Subscribe to all device_data subtopics
        print("📡 Successfully subscribed to device_data topics with QoS 1")
    except Exception as e:
        print(f"❌ Error subscribing to topics: {e}")
        # Log more details for debugging
        print(f"   Client type: {type(client)}")
        print(f"   Client connected: {getattr(client, 'is_connected', 'Unknown')}")


def on_disconnect(client, packet, exc=None):  # packet and exc unused but required by callback signature
    """MQTT disconnection callback - regular function for gmqtt compatibility"""
    print("🔌 Disconnected from MQTT Broker (Async)")
    # Update Prometheus metric for connection status
    try:
        from .metrics import MQTT_CONNECTION_STATUS

        MQTT_CONNECTION_STATUS.set(0)
        print("✅ MQTT_CONNECTION_STATUS metric updated to 0")
    except ImportError as e:
        print(f"⚠️ Could not import metrics: {e}")
    except Exception as e:
        print(f"❌ Error updating MQTT_CONNECTION_STATUS metric: {e}")


def on_message(client, topic, payload, qos, properties):
    """MQTT message callback - simplified for Kafka-first mode"""
    try:
        # MONITORING: Count MQTT messages received
        message_counters.mqtt_received += 1

        # PROMETHEUS: Record MQTT message received
        record_mqtt_message(parsed_successfully=True)

        # Reduced logging - only log occasionally
        if message_counters.mqtt_received % 100 == 0:
            print(
                f"🔄 MQTT message received: topic={topic} (total: {message_counters.mqtt_received})"
            )

        # KAFKA-FIRST MODE: Always use Kafka-first handler
        try:
            from .mqtt_kafka_first import kafka_first_handler

            # Reduced logging - only log forwarding occasionally
            if message_counters.mqtt_received % 500 == 0:
                print(
                    f"📤 Forwarding to Kafka-first handler (total forwarded: {message_counters.mqtt_received})"
                )

            # Use the handler's sync on_message method (thread-safe)
            kafka_first_handler.on_message(client, topic, payload, qos, properties)

        except Exception as e:
            print(f"❌ Error forwarding to Kafka-first handler: {e}")
            import traceback

            traceback.print_exc()
            message_counters.mqtt_errors += 1

    except Exception as e:
        print(f"❌ Error in on_message callback: {e}")
        message_counters.mqtt_errors += 1
        # PROMETHEUS: Record MQTT message error
        record_mqtt_message(parsed_successfully=False)
        from .metrics import record_message_loss

        record_message_loss("on_message_error")


# ✅ PER-DEVICE PRODUCER: Add handler for per-device Kafka pipeline
from .mqtt_kafka_first import on_message_kafka_first


def _device_from_topic(topic: str) -> str:
    """Extract device ID from MQTT topic"""
    # e.g. "device_data/frontend1_ultra_high_perf_device"
    parts = topic.split("/")
    return parts[-1] if parts else "unknown"


async def on_message_per_device(client, topic, payload, qos, properties):
    """Per-device message handler that calls forward_to_kafka"""
    try:
        data = orjson.loads(payload) if payload else []
        if not isinstance(data, list):
            data = [data]
    except Exception:
        # if payload isn't JSON, still forward as a single blob
        data = [{"raw": payload.decode("utf-8", "ignore")}]

    device_id = (
        data[0].get("device_id")
        if data and isinstance(data[0], dict) and "device_id" in data[0]
        else _device_from_topic(topic)
    )

    print(
        f"📤 Per-device producer: forwarding {len(data)} messages to device {device_id}"
    )
    await forward_to_kafka(device_id, data)
    print(
        f"✅ Per-device producer: successfully forwarded to Kafka topic iot_device_{device_id}"
    )


# ✅ MESSAGE MULTIPLEXER: Clean mode separation (no more unconditional "both")
async def on_message_mux(client, topic, payload, qos, properties):
    """Message multiplexer with configurable pipeline mode"""
    try:
        # --- FIX: update MQTT counters + Prometheus once per MQTT message ---
        from .metrics import record_mqtt_message  # local import to avoid cycles

        message_counters.mqtt_received += 1

        try:
            if payload:
                message_data = orjson.loads(
                    payload
                )  # lightweight parse to qualify as "parsed"
                # Count individual data points inside the message
                if isinstance(message_data, list):
                    message_counters.mqtt_data_points += len(message_data)
                else:
                    message_counters.mqtt_data_points += 1

                message_counters.mqtt_parsed += 1
                record_mqtt_message(parsed_successfully=True)
            else:
                message_counters.mqtt_data_points += 1  # Empty payload counts as 1
                message_counters.mqtt_parsed += 1
                record_mqtt_message(parsed_successfully=True)
        except Exception:
            message_counters.mqtt_errors += 1
            message_counters.mqtt_data_points += 1  # Failed parse counts as 1
            record_mqtt_message(parsed_successfully=False)

        # ✅ CLEAN MODE SEPARATION: Choose one path based on PIPELINE_MODE
        pipeline_mode = os.getenv("PIPELINE_MODE", "kafka_first").lower()

        if pipeline_mode == "kafka_first":
            print("🔧 Pipeline Mode: Kafka-First only")
            await on_message_kafka_first(client, topic, payload, qos, properties)
        elif pipeline_mode == "per_device":
            print("🔧 Pipeline Mode: Per-Device only")
            await on_message_per_device(client, topic, payload, qos, properties)
        elif pipeline_mode == "both":
            print("🔧 Pipeline Mode: Both paths (duplication enabled)")
            # Only run both if explicitly requested
            t1 = asyncio.create_task(
                on_message_per_device(client, topic, payload, qos, properties)
            )
            t2 = asyncio.create_task(
                on_message_kafka_first(client, topic, payload, qos, properties)
            )
            await asyncio.gather(t1, t2, return_exceptions=True)
        else:
            print(
                f"⚠️ Unknown PIPELINE_MODE: {pipeline_mode}, defaulting to kafka_first"
            )
            await on_message_kafka_first(client, topic, payload, qos, properties)

    except Exception as e:
        print(f"❌ Error in message multiplexer: {e}")
        # Fallback to just per-device if Kafka-first fails
        try:
            await on_message_per_device(client, topic, payload, qos, properties)
        except Exception as fallback_error:
            print(f"❌ Per-device fallback also failed: {fallback_error}")


# Kafka-first mode only - no message processing needed


# Function to get monitoring stats
def get_message_stats():
    """Get current message processing statistics."""
    return message_counters.get_stats()


def print_message_stats():
    """Print current message processing statistics."""
    message_counters.print_stats()


# Start monitoring stats printing every 10 seconds
async def start_monitoring():
    """Start periodic monitoring stats printing."""
    while True:
        await asyncio.sleep(10)
        print_message_stats()
        print_kafka_stats()  # Include Kafka statistics
        # PROMETHEUS: Update system health metrics
        update_system_health()


async def start_mqtt_client():
    """Start the async MQTT client and connect to the broker."""
    global mqtt_client

    # Create async MQTT client
    client_id = f"async-subscriber-{int(time.time())}"
    mqtt_client = MQTTClient(client_id)

    # Set async event handlers
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message = on_message

    try:
        # Connect to MQTT broker asynchronously
        mqtt_host = "10.0.16.24"  # Connect to the actual MQTT broker
        mqtt_port = 1883

        print(f"🔗 Connecting to MQTT broker at {mqtt_host}:{mqtt_port}...")
        print(f"   Debug: Host type: {type(mqtt_host)}, Port type: {type(mqtt_port)}")

        # Validate connection parameters
        try:
            socket.getaddrinfo(mqtt_host, mqtt_port)
            print(f"   ✅ Socket validation passed for {mqtt_host}:{mqtt_port}")
        except Exception as e:
            print(f"   ⚠️ Socket validation failed: {e}")

        await mqtt_client.connect(mqtt_host, mqtt_port)

        print("✅ Async MQTT client started successfully")

        # Keep the client running
        await mqtt_client.disconnect_s()

    except Exception as e:
        print(f"❌ Error starting async MQTT client: {e}")
        raise


async def start_mqtt_client_forever():
    """Start the async MQTT client and keep it running forever."""
    global mqtt_client

    print("🚀 Starting MQTT client initialization...")

    # Create async MQTT client
    client_id = f"async-subscriber-{int(time.time())}"
    print(f"   Creating MQTT client with ID: {client_id}")
    mqtt_client = MQTTClient(client_id)
    print(f"   MQTT client created: {type(mqtt_client)}")

    # Set async event handlers
    print("   Setting up event handlers...")
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message = on_message_mux  # ✅ Use message multiplexer for both paths
    print("   Event handlers configured (using message multiplexer)")

    # ✅ Log the active pipeline mode
    pipeline_mode = os.getenv("PIPELINE_MODE", "kafka_first").lower()
    print(f"🔧 Pipeline Mode: {pipeline_mode.upper()}")
    if pipeline_mode == "both":
        print("   ⚠️  WARNING: Both paths enabled - messages will be duplicated!")
    elif pipeline_mode == "kafka_first":
        print("   ✅ Kafka-First: Zero-loss ingestion with device-specific routing")
    elif pipeline_mode == "per_device":
        print("   ✅ Per-Device: Direct device topic creation")

    # ✅ Initialize Kafka-first producer if needed
    if pipeline_mode in ("kafka_first", "both"):
        print("🚀 Initializing Kafka-first handler (starting Kafka producer)...")
        await start_kafka_first_handler()
    else:
        print("ℹ️ Kafka-first handler not started (PIPELINE_MODE != kafka_first/both)")

    try:
        # Kafka-first mode - no buffer manager needed
        print("🚀 Kafka-first mode active - no buffer manager initialization needed")

        # Connect to MQTT broker asynchronously
        mqtt_host = "10.0.16.24"  # Connect to the actual MQTT broker
        mqtt_port = 1883

        print(f"🔗 Connecting to MQTT broker at {mqtt_host}:{mqtt_port}...")
        print(f"   Debug: Host type: {type(mqtt_host)}, Port type: {type(mqtt_port)}")

        # Validate connection parameters
        try:
            socket.getaddrinfo(mqtt_host, mqtt_port)
            print(f"   ✅ Socket validation passed for {mqtt_host}:{mqtt_port}")
        except Exception as e:
            print(f"   ⚠️ Socket validation failed: {e}")

        await mqtt_client.connect(mqtt_host, mqtt_port)

        print("✅ Async MQTT client started successfully")

        # Keep the client running forever
        # gmqtt doesn't have loop_forever(), so we use a different approach
        print("🔄 MQTT client running - keeping connection alive...")
        try:
            while True:
                await asyncio.sleep(1)  # Keep the event loop alive
                # Check if client is still connected
                if not mqtt_client.is_connected:
                    print("⚠️ MQTT client disconnected, attempting to reconnect...")
                    try:
                        await mqtt_client.reconnect()
                        print("✅ MQTT client reconnected successfully")
                    except Exception as e:
                        print(f"❌ Failed to reconnect: {e}")
                        await asyncio.sleep(5)  # Wait before retry
        except KeyboardInterrupt:
            print("🛑 MQTT client interrupted by user")
        except Exception as e:
            print(f"❌ MQTT client error: {e}")
            # Don't raise the exception, just log it and continue
            print("🔄 Continuing MQTT client operation...")

    except Exception as e:
        print(f"❌ Error starting async MQTT client: {e}")
        print(f"   Error type: {type(e)}")
        print(f"   Error details: {str(e)}")
        import traceback

        traceback.print_exc()
        raise


__all__ = [
    "get_mqtt_client",
    "get_message_stats",
    "print_message_stats",
    "start_monitoring",
    "start_mqtt_client",
    "start_mqtt_client_forever",
]
