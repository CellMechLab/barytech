#!/usr/bin/env python3
"""
Frontend-2 High Performance Publisher
A high-performance MQTT publisher that sends 10,000 points with device-specific topic optimization
"""

import paho.mqtt.client as mqtt
import json
import time
import random
import threading
from datetime import datetime
import asyncio
import concurrent.futures

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
BASE_TOPIC = "device_data"

class HighPerformancePublisher:
    def __init__(self):
        self.client = mqtt.Client(client_id="frontend2_high_perf_publisher", protocol=mqtt.MQTTv311, clean_session=True)
        self.client.on_connect = self.on_connect
        self.client.on_publish = self.on_publish
        self.client.on_disconnect = self.on_disconnect
        self.client.on_log = self.on_log
        
        # High-performance MQTT client settings
        self.client.max_inflight_messages_set(200000)
        self.client.max_queued_messages_set(1000000)
        
        # High-performance settings
        self.device_id = "frontend2_high_perf_device"
        self.message_count = 0
        self.messages_published = 0
        self.is_running = False
        self.target_rate = 5000  # 5,000 messages per second (optimized)
        self.total_messages = 100000  # 100,000 total messages
        self.batch_size = 100  # Smaller batches for better control
        self.connection_established = False
        
        # Device-specific topic for optimization
        self.topic = f"{BASE_TOPIC}/{self.device_id}"
        
        # Performance tracking
        self.start_time = None
        self.last_report_time = 0
        self.report_interval = 1.0  # Report every second
        
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"✅ Frontend-2 High Performance Publisher connected to MQTT broker")
            print(f"📊 Configuration:")
            print(f"   - Device ID: {self.device_id}")
            print(f"   - Target Rate: {self.target_rate:,} msg/sec")
            print(f"   - Total Messages: {self.total_messages:,}")
            print(f"   - Batch Size: {self.batch_size}")
            print(f"   - Topic: {self.topic}")
            self.connection_established = True
        else:
            print(f"❌ Connection failed with code {rc}")
            
    def on_publish(self, client, userdata, mid):
        self.messages_published += 1
        
        # Performance reporting
        current_time = time.time()
        if current_time - self.last_report_time >= self.report_interval:
            elapsed = current_time - self.start_time if self.start_time else 0
            rate = self.messages_published / elapsed if elapsed > 0 else 0
            progress = (self.messages_published / self.total_messages) * 100
            print(f"📤 Progress: {self.messages_published:,}/{self.total_messages:,} ({progress:.1f}%) - Rate: {rate:,.0f} msg/sec")
            self.last_report_time = current_time
            
    def on_disconnect(self, client, userdata, rc):
        print(f"🔌 Frontend-2 High Performance Publisher disconnected (rc={rc})")
        self.connection_established = False
        
    def on_log(self, client, userdata, level, buf):
        # Only log errors and warnings
        if level <= mqtt.MQTT_LOG_WARNING:
            print(f"🔍 MQTT Log [{level}]: {buf}")
        
    def generate_data_point(self, message_id):
        """Generate a realistic data point with high-frequency variations"""
        timestamp = datetime.utcnow().isoformat()
        
        # Generate realistic displacement and force values with high-frequency noise
        # Simulate a sensor reading with rapid variations
        base_displacement = 15.0 + (message_id * 0.001)  # Gradual increase, different from frontend-1
        noise_displacement = random.uniform(-2.0, 2.0)  # High-frequency noise
        displacement = base_displacement + noise_displacement
        
        # Force correlates with displacement but with some variation
        base_force = displacement * 3.0 + random.uniform(-2, 2)  # Different scaling from frontend-1
        force = max(0, base_force)  # Force should be positive
        
        return {
            "device_id": self.device_id,
            "timestamp": timestamp,
            "displacement": round(displacement, 3),
            "force": round(force, 3),
            "message_id": message_id,
            "publisher": "frontend2_high_perf_publisher",
            "batch_id": message_id // self.batch_size
        }
        

            
    def publish_data(self):
        """Publish data at high performance"""
        if not self.connection_established:
            print("❌ Cannot start publishing - not connected")
            return
            
        self.start_time = time.time()
        self.last_report_time = self.start_time
        self.is_running = True
        
        print(f"🚀 Starting high-performance publishing...")
        
        # Calculate timing
        batches_per_second = self.target_rate / self.batch_size
        batch_interval = 1.0 / batches_per_second
        
        print(f"📊 Timing:")
        print(f"   - Batches per second: {batches_per_second:.1f}")
        print(f"   - Batch interval: {batch_interval:.3f} seconds")
        
        message_id = 1
        while self.is_running and message_id <= self.total_messages:
            batch_start_time = time.time()
            
            # Calculate batch size
            remaining_messages = self.total_messages - message_id + 1
            current_batch_size = min(self.batch_size, remaining_messages)
            
            # Publish batch
            published = self.publish_batch_and_count(message_id, current_batch_size)
            message_id += current_batch_size
            
            # Wait for next batch (if needed)
            elapsed = time.time() - batch_start_time
            if elapsed < batch_interval:
                time.sleep(batch_interval - elapsed)
                
        # Final statistics
        elapsed = time.time() - self.start_time
        avg_rate = self.messages_published / elapsed if elapsed > 0 else 0
        
        print(f"\n📊 Frontend-2 High Performance Publisher Statistics:")
        print(f"   - Messages Sent: {self.message_count:,}")
        print(f"   - Messages Published: {self.messages_published:,}")
        print(f"   - Total Time: {elapsed:.2f} seconds")
        print(f"   - Average Rate: {avg_rate:,.0f} msg/sec")
        print(f"   - Target Rate: {self.target_rate:,} msg/sec")
        print(f"   - Performance: {(avg_rate/self.target_rate)*100:.1f}% of target")
        print(f"   - Topic Used: {self.topic}")
        
        # Wait for any remaining messages to be published
        print("⏳ Waiting for remaining messages...")
        time.sleep(2)
        
    def publish_batch_and_count(self, start_id, count):
        """Publish a batch of messages efficiently and return count"""
        if not self.connection_established:
            print("❌ Not connected to broker")
            return 0
            
        published_count = 0
        for i in range(count):
            if not self.is_running:
                break
                
            message_id = start_id + i
            data = self.generate_data_point(message_id)
            payload = json.dumps(data)
            
            try:
                result = self.client.publish(self.topic, payload, qos=0, retain=False)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    published_count += 1
                    self.message_count += 1
                else:
                    print(f"❌ Publish failed for message {message_id}: {result.rc}")
            except Exception as e:
                print(f"❌ Exception publishing message {message_id}: {e}")
                
        return published_count
        
    def start(self):
        """Start the high-performance publisher"""
        try:
            # Connect to MQTT broker
            print(f"🔗 Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            
            # Start MQTT loop
            self.client.loop_start()
            
            # Wait for connection
            timeout = 10
            while not self.connection_established and timeout > 0:
                time.sleep(0.1)
                timeout -= 0.1
                
            if not self.connection_established:
                print("❌ Connection timeout")
                return
                
            # Start publishing
            self.publish_data()
            
        except KeyboardInterrupt:
            print(f"\n⏹️  Stopping Frontend-2 High Performance Publisher...")
            self.is_running = False
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            print("🔌 Frontend-2 Publisher stopped")

def main():
    """Main function to run the High Performance Publisher"""
    print("=" * 80)
    print("🚀 Frontend-2 High Performance Publisher")
    print("=" * 80)
    print("This publisher sends 100,000 points with device-specific topic optimization")
    print("Make sure:")
    print("1. MQTT broker (mosquitto) is running")
    print("2. Backend is running on port 8000")
    print("3. frontend-2 React app is running on port 3002")
    print("4. System can handle high message rates")
    print("=" * 80)
    
    publisher = HighPerformancePublisher()
    publisher.start()

if __name__ == "__main__":
    main()
