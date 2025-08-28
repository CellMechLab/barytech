import paho.mqtt.client as mqtt
from app.message_processor import process_message_batches, process_message_batches
import asyncio
import app.shared_state
import time
import queue
import orjson
from app.metrics import record_mqtt_message, record_message_type, record_e2e_latency, update_system_health

mqtt_client = None

# Global counter for total received messages
total_messages_received = 0
# Message rate monitoring
last_message_count = 0
last_rate_check = time.time()

# Thread-safe queue for messages from MQTT thread to async event loop
message_queue = queue.Queue(maxsize=0)  # Unbounded, thread-safe queue

# Monitoring counters for each stage
class MessageCounters:
    def __init__(self):
        self.mqtt_received = 0
        self.mqtt_parsed = 0
        self.mqtt_errors = 0
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
            "device_queued": self.device_queued,
            "device_processed": self.device_processed,
            "broadcast_sent": self.broadcast_sent,
            "broadcast_errors": self.broadcast_errors,
            "db_saved": self.db_saved,
            "db_errors": self.db_errors,
            "elapsed_time": elapsed,
            "mqtt_rate": self.mqtt_received / elapsed if elapsed > 0 else 0,
            "processing_rate": self.device_processed / elapsed if elapsed > 0 else 0,
            "broadcast_rate": self.broadcast_sent / elapsed if elapsed > 0 else 0,
            "db_rate": self.db_saved / elapsed if elapsed > 0 else 0
        }
    
    def print_stats(self):
        stats = self.get_stats()
        print(f"\n📊 MESSAGE PROCESSING STATS:")
        print(f"   MQTT Received: {stats['mqtt_received']} ({stats['mqtt_rate']:.1f}/sec)")
        print(f"   MQTT Parsed: {stats['mqtt_parsed']} ({(stats['mqtt_parsed']/stats['mqtt_received']*100):.1f}% success)")
        print(f"   MQTT Errors: {stats['mqtt_errors']}")
        print(f"   Device Queued: {stats['device_queued']}")
        print(f"   Device Processed: {stats['device_processed']} ({stats['processing_rate']:.1f}/sec)")
        print(f"   Broadcast Sent: {stats['broadcast_sent']} ({stats['broadcast_rate']:.1f}/sec)")
        print(f"   Broadcast Errors: {stats['broadcast_errors']}")
        print(f"   DB Saved: {stats['db_saved']} ({stats['db_rate']:.1f}/sec)")
        print(f"   DB Errors: {stats['db_errors']}")
        print(f"   Elapsed Time: {stats['elapsed_time']:.1f} seconds")

# Global monitoring instance
message_counters = MessageCounters()

def get_mqtt_client():
    global mqtt_client
    if mqtt_client is None:
        raise RuntimeError("MQTT client is not initialized!")
    return mqtt_client

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT Broker!")
        # Update Prometheus metric for connection status
        from app.metrics import MQTT_CONNECTION_STATUS
        MQTT_CONNECTION_STATUS.set(1)
        
        client.subscribe("MON", qos=1)
        client.subscribe("device_data", qos=1)  # Subscribe to base device_data topic
        client.subscribe("device_data/#", qos=1)  # Subscribe to all device-specific topics
        print("Subscribed to topics: MON, device_data, device_data/#")
    else:
        print(f"Failed to connect, return code {rc}")
        # Update Prometheus metric for connection status
        from app.metrics import MQTT_CONNECTION_STATUS
        MQTT_CONNECTION_STATUS.set(0)

def on_disconnect(client, userdata, rc):
    print(f"Disconnected from MQTT Broker with code {rc}")
    # Update Prometheus metric for connection status
    from app.metrics import MQTT_CONNECTION_STATUS
    MQTT_CONNECTION_STATUS.set(0)

def on_message(client, userdata, msg):
    """Callback for processing received MQTT messages."""
    try:
        # MONITORING: Count MQTT messages received
        message_counters.mqtt_received += 1
        
        # PROMETHEUS: Record MQTT message received
        record_mqtt_message(parsed_successfully=True)
        
        # OPTIMAL APPROACH: Thread-safe queue for message storage
        # Push raw message payload directly into thread-safe queue
        try:
            message_queue.put_nowait(msg.payload)
        except queue.Full:
            print("⚠️  Warning: Message queue full - dropping message")
            message_counters.mqtt_errors += 1
            # PROMETHEUS: Record message loss
            from app.metrics import record_message_loss
            record_message_loss("queue_full")
            # In practice, with maxsize=0 (unbounded), this should never happen
            # But good to have the safety check
    except Exception as e:
        print(f"Error in on_message callback: {e}")
        message_counters.mqtt_errors += 1
        # PROMETHEUS: Record MQTT message error
        record_mqtt_message(parsed_successfully=False)
        from app.metrics import record_message_loss
        record_message_loss("on_message_error")

async def process_raw_messages():
    """Process raw messages from MQTT thread efficiently using thread-safe queue."""
    print("Raw message processor started (thread-safe queue)")
    
    # Configuration for batch processing
    MAX_BATCH_SIZE = 2000  # Increased batch size for better throughput
    BATCH_TIMEOUT = 0.01   # Maximum time to wait for batch completion
    
    while True:
        try:
            # Collect batch of messages from thread-safe queue
            batch = []
            start_time = time.time()
            
            # Try to collect messages up to MAX_BATCH_SIZE or timeout
            while len(batch) < MAX_BATCH_SIZE and (time.time() - start_time) < BATCH_TIMEOUT:
                try:
                    payload = message_queue.get_nowait()
                    batch.append(payload)
                except queue.Empty:
                    # No more messages available, break out of collection loop
                    break
            
            # Process batch if we have messages
            if batch:
                print(f"Processing batch of {len(batch)} raw messages from thread-safe queue")
                
                # PROMETHEUS: Record batch processing
                from app.metrics import record_batch_processing
                record_batch_processing(len(batch), time.time() - start_time)
                
                await process_raw_message_batch(batch)
            else:
                # No messages, sleep briefly to avoid busy-waiting
                await asyncio.sleep(0.001)
                        
        except Exception as e:
            print(f"Error in raw message processor: {e}")
            await asyncio.sleep(0.01)
    
async def process_raw_message_batch(raw_messages: list):
    """Process a batch of raw messages efficiently with optimized JSON parsing."""
    try:
        # Import here to avoid circular imports
        from app.message_processor import device_queues, device_config, start_device_broadcaster
        
        # Group messages by device
        device_messages = {}
        parsed_count = 0
        error_count = 0
        
        # OPTIMIZED: Parse JSON in batches to reduce Python overhead
        for raw_payload in raw_messages:
            try:
                # Parse JSON using orjson for fastest processing
                message_content = orjson.loads(raw_payload)
                parsed_count += 1
                
                # PROMETHEUS: Record message type
                if isinstance(message_content, list):
                    # This is a batched message from optimized publishers
                    batch_size = len(message_content)
                    print(f"Processing batched message with {batch_size} data points")
                    record_message_type(is_batched=True, batch_size=batch_size)
                    
                    # Process all data points in the batch
                    for data_point in message_content:
                        device_id = data_point.get("device_id")
                        if device_id:
                            if device_id not in device_messages:
                                device_messages[device_id] = []
                            device_messages[device_id].append(data_point)
                else:
                    # This is a single message (legacy format)
                    record_message_type(is_batched=False)
                    device_id = message_content.get("device_id")
                    if device_id:
                        if device_id not in device_messages:
                            device_messages[device_id] = []
                        device_messages[device_id].append(message_content)
                    
            except Exception as e:
                error_count += 1
                print(f"Error parsing message {error_count}: {e}")
                # PROMETHEUS: Record parse error
                record_mqtt_message(parsed_successfully=False)
                continue
        
        # MONITORING: Update parsing statistics
        message_counters.mqtt_parsed += parsed_count
        message_counters.mqtt_errors += error_count
        
        # Process each device's messages
        for device_id, messages in device_messages.items():
            # Initialize device config if needed
            if device_id not in device_config:
                device_config[device_id] = {"save_flag": False}
            
            # Ensure broadcaster is started for this device
            await start_device_broadcaster(device_id)
            
            # Put messages in device queue for broadcasting
            if device_id not in device_queues:
                device_queues[device_id] = asyncio.Queue()
                
            for message in messages:
                try:
                    device_queues[device_id].put_nowait(message)
                    # MONITORING: Count messages queued for device processing
                    message_counters.device_queued += 1
                except asyncio.QueueFull:
                    print(f"Warning: Device queue full for {device_id}")
                    message_counters.mqtt_errors += 1
                    # PROMETHEUS: Record message loss
                    from app.metrics import record_message_loss
                    record_message_loss("device_queue_full")
                    break
            
            # Save messages if save flag is enabled
            import app.shared_state
            if app.shared_state.save_flag:
                from app.message_processor import device_save_queues, start_device_saver
                await start_device_saver(device_id)
                for message in messages:
                    try:
                        device_save_queues[device_id].put_nowait(message)
                    except asyncio.QueueFull:
                        print(f"Warning: Save queue full for {device_id}")
                        message_counters.db_errors += 1
                        # PROMETHEUS: Record message loss
                        from app.metrics import record_message_loss
                        record_message_loss("save_queue_full")
                        break
        
        total_points = sum(len(messages) for messages in device_messages.values())
        print(f"JSON Parsing Stats: {parsed_count} parsed, {error_count} errors")
        print(f"Processed {len(raw_messages)} raw messages into {total_points} data points for {len(device_messages)} devices")
        
    except Exception as e:
        print(f"Error processing raw message batch: {e}")
        message_counters.mqtt_errors += len(raw_messages)
        # PROMETHEUS: Record message loss
        from app.metrics import record_message_loss
        record_message_loss("batch_processing_error", len(raw_messages))

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
        # PROMETHEUS: Update system health metrics
        update_system_health()

def start_mqtt_client():
    """Start the MQTT client and connect to the broker."""
    global mqtt_client
    
    # Create MQTT client
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message = on_message
    
    # Set MQTT client options for high performance
    mqtt_client.max_inflight_messages_set(10000)
    mqtt_client.max_queued_messages_set(10000)
    
    try:
        # Connect to MQTT broker
        mqtt_client.connect("localhost", 1883, 60)
        
        # Start the MQTT client loop in a separate thread
        mqtt_client.loop_start()
        
        print("MQTT client started successfully")
        
    except Exception as e:
        print(f"Error starting MQTT client: {e}")
        raise

__all__ = ["get_mqtt_client", "get_message_stats", "print_message_stats", "start_monitoring", "start_mqtt_client"]
