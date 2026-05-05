#!/usr/bin/env python3
"""
Frontend-1 Publisher
A simple MQTT publisher that sends data specifically for testing frontend-1 with device-specific topic optimization
"""

import paho.mqtt.client as mqtt
import json
import time
import random
import threading
from datetime import datetime

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
BASE_TOPIC = "device_data"

class Frontend1Publisher:
    def __init__(self):
        self.client = mqtt.Client(client_id="frontend1_publisher", protocol=mqtt.MQTTv311, clean_session=False)
        self.client.on_connect = self.on_connect
        self.client.on_publish = self.on_publish
        self.client.on_disconnect = self.on_disconnect
        
        # Publisher settings
        self.device_id = "frontend1_device"
        self.message_count = 0
        self.is_running = False
        self.target_rate = 100  # messages per second
        self.total_messages = 1000  # total messages to send
        
        # Device-specific topic for optimization
        self.topic = f"{BASE_TOPIC}/{self.device_id}"
        
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"✅ Frontend-1 Publisher connected to MQTT broker")
            print(f"📊 Configuration:")
            print(f"   - Device ID: {self.device_id}")
            print(f"   - Target Rate: {self.target_rate} msg/sec")
            print(f"   - Total Messages: {self.total_messages}")
            print(f"   - Topic: {self.topic}")
            print(f"🚀 Starting data transmission...")
        else:
            print(f"❌ Connection failed with code {rc}")
            
    def on_publish(self, client, userdata, mid):
        self.message_count += 1
        if self.message_count % 100 == 0:
            elapsed = time.time() - self.start_time
            rate = self.message_count / elapsed if elapsed > 0 else 0
            print(f"📤 Sent {self.message_count}/{self.total_messages} messages (rate: {rate:.1f} msg/sec)")
            
    def on_disconnect(self, client, userdata, rc):
        print(f"🔌 Frontend-1 Publisher disconnected")
        
    def generate_data_point(self):
        """Generate a realistic data point for frontend-1"""
        timestamp = datetime.utcnow().isoformat()
        
        # Generate realistic displacement and force values
        # Simulate a sensor reading with some noise
        base_displacement = 10.0 + (self.message_count * 0.1)  # Gradually increasing
        noise_displacement = random.uniform(-0.5, 0.5)
        displacement = base_displacement + noise_displacement
        
        # Force correlates with displacement but with some variation
        base_force = displacement * 2.5 + random.uniform(-1, 1)
        force = max(0, base_force)  # Force should be positive
        
        return {
            "device_id": self.device_id,
            "timestamp": timestamp,
            "displacement": round(displacement, 3),
            "force": round(force, 3),
            "message_id": self.message_count + 1,
            "publisher": "frontend1_publisher"
        }
        
    def publish_data(self):
        """Publish data at the specified rate"""
        self.start_time = time.time()
        self.is_running = True
        
        while self.is_running and self.message_count < self.total_messages:
            # Generate data point
            data = self.generate_data_point()
            
            # Convert to JSON
            payload = json.dumps(data)
            
            # Publish to MQTT with device-specific topic
            result = self.client.publish(self.topic, payload, qos=1, retain=False)
            
            # Wait to maintain target rate
            time.sleep(1.0 / self.target_rate)
            
        # Final statistics
        elapsed = time.time() - self.start_time
        avg_rate = self.message_count / elapsed if elapsed > 0 else 0
        print(f"\n📊 Frontend-1 Publisher Statistics:")
        print(f"   - Total Messages Sent: {self.message_count}")
        print(f"   - Total Time: {elapsed:.2f} seconds")
        print(f"   - Average Rate: {avg_rate:.1f} msg/sec")
        print(f"   - Target Rate: {self.target_rate} msg/sec")
        print(f"   - Topic Used: {self.topic}")
        
        # Disconnect
        self.client.disconnect()
        
    def start(self):
        """Start the publisher"""
        try:
            # Connect to MQTT broker
            print(f"🔗 Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            
            # Start publishing in a separate thread
            publish_thread = threading.Thread(target=self.publish_data)
            publish_thread.daemon = True
            publish_thread.start()
            
            # Start the MQTT loop
            self.client.loop_forever()
            
        except KeyboardInterrupt:
            print(f"\n⏹️  Stopping Frontend-1 Publisher...")
            self.is_running = False
            self.client.disconnect()
        except Exception as e:
            print(f"❌ Error: {e}")
            self.client.disconnect()

def main():
    """Main function to run the Frontend-1 Publisher"""
    print("=" * 60)
    print("🚀 Frontend-1 Publisher")
    print("=" * 60)
    print("This publisher sends data specifically for testing frontend-1 with device-specific topic optimization")
    print("Make sure:")
    print("1. MQTT broker (mosquitto) is running")
    print("2. Backend is running on port 8000")
    print("3. frontend-1.html is open in browser")
    print("=" * 60)
    
    publisher = Frontend1Publisher()
    publisher.start()

if __name__ == "__main__":
    main()
