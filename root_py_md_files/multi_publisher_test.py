import time
import math
import threading
import paho.mqtt.client as mqtt
import orjson
from datetime import datetime
import random

# Test Configuration
POINTS_PER_SECOND = 10000
TOTAL_POINTS = 30000
DEVICE_IDS = ["device_001", "device_002", "device_003"]

# MQTT Broker settings
broker = "127.0.0.1"
port = 1883
topic = "MON"

def generate_displacement(index):
    min_val = -1.2168244889861554e-6
    max_val = -3.203646967473276e-8
    scale = (max_val - min_val) / 2
    offset = (max_val + min_val) / 2
    return offset + scale * math.sin(math.radians(index))

def generate_force(index):
    base = 5e-12 * math.sin(math.radians(index * 3))
    noise = random.uniform(-5e-13, 5e-13)
    return base + noise

def publisher(producer_id, device_id):
    """Individual publisher for a specific device"""
    print(f"Starting Publisher {producer_id} for Device {device_id}")
    print(f"  - Rate: {POINTS_PER_SECOND:,} points/second")
    print(f"  - Total: {TOTAL_POINTS:,} points")
    
    # Create MQTT client
    client = mqtt.Client(client_id=f"publisher_{producer_id}_{device_id}", protocol=mqtt.MQTTv311, clean_session=False)
    
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print(f"Publisher {producer_id} connected successfully")
        else:
            print(f"Publisher {producer_id} connection failed with code {rc}")
    
    client.on_connect = on_connect
    client.connect(broker, port, 60)
    client.loop_start()
    
    # Calculate timing for rate limiting
    batch_size = 1000  # Send in batches for efficiency
    sleep_time = batch_size / POINTS_PER_SECOND
    
    total_messages_sent = 0
    start_time = time.time()
    
    try:
        while total_messages_sent < TOTAL_POINTS:
            batch_start = time.time()
            
            # Send a batch of messages
            for i in range(batch_size):
                if total_messages_sent >= TOTAL_POINTS:
                    break
                
                disp = generate_displacement(total_messages_sent)
                force = generate_force(total_messages_sent)
                timestamp = datetime.now().isoformat()
                
                payload = {
                    "device_id": device_id,
                    "device_token": f"token_{device_id}",
                    "timestamp": timestamp,
                    "displacement": disp,
                    "force": force,
                    "producer_id": producer_id,
                    "message_id": total_messages_sent
                }
                
                # Use retain=False for streaming telemetry
                client.publish(topic, orjson.dumps(payload), qos=1, retain=False)
                
                total_messages_sent += 1
            
            # Rate limiting
            batch_time = time.time() - batch_start
            if batch_time < sleep_time:
                time.sleep(sleep_time - batch_time)
            
            # Progress update
            if total_messages_sent % 5000 == 0:
                elapsed = time.time() - start_time
                rate = total_messages_sent / elapsed if elapsed > 0 else 0
                print(f"Publisher {producer_id}: {total_messages_sent:,}/{TOTAL_POINTS:,} messages sent (rate: {rate:.0f} msg/sec)")
    
    except KeyboardInterrupt:
        print(f"Publisher {producer_id} interrupted by user")
    
    finally:
        # Give a moment for any in-flight QoS1 messages to complete
        time.sleep(0.5)
        client.loop_stop()
        client.disconnect()
        
        elapsed = time.time() - start_time
        final_rate = total_messages_sent / elapsed if elapsed > 0 else 0
        print(f"Publisher {producer_id} finished: {total_messages_sent:,} messages in {elapsed:.2f}s (avg rate: {final_rate:.0f} msg/sec)")

def main():
    print("=== Multi-Publisher Stress Test ===")
    print(f"Configuration:")
    print(f"  - Publishers: {len(DEVICE_IDS)}")
    print(f"  - Rate per publisher: {POINTS_PER_SECOND:,} points/second")
    print(f"  - Total per publisher: {TOTAL_POINTS:,} points")
    print(f"  - Total messages: {len(DEVICE_IDS) * TOTAL_POINTS:,}")
    print(f"  - Expected total rate: {len(DEVICE_IDS) * POINTS_PER_SECOND:,} points/second")
    print("=" * 50)
    
    # Create and start publisher threads
    threads = []
    for i, device_id in enumerate(DEVICE_IDS):
        thread = threading.Thread(
            target=publisher,
            args=(i + 1, device_id),
            daemon=True
        )
        threads.append(thread)
        thread.start()
        time.sleep(0.1)  # Small delay between publishers
    
    print(f"\nAll {len(DEVICE_IDS)} publishers started!")
    print("Press Ctrl+C to stop all publishers")
    
    try:
        # Wait for all publishers to complete
        for thread in threads:
            thread.join()
        
        print("\n=== All Publishers Finished ===")
        
    except KeyboardInterrupt:
        print("\nStopping all publishers...")
        # Threads are daemon, so they'll stop when main thread exits

if __name__ == "__main__":
    main()
