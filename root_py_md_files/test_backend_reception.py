#!/usr/bin/env python3
"""
Test Backend Reception
A simple test to verify the backend is receiving MQTT messages
"""

import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPIC = "device_data"

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Test client connected to MQTT broker")
        client.subscribe(TOPIC, qos=1)
        print(f"📡 Subscribed to topic: {TOPIC}")
    else:
        print(f"❌ Connection failed with code {rc}")

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        print(f"📨 Received message: {data}")
    except Exception as e:
        print(f"❌ Error parsing message: {e}")

def test_backend_reception():
    """Test if backend is receiving messages"""
    print("=" * 60)
    print("🧪 Backend Reception Test")
    print("=" * 60)
    
    # Create test client
    client = mqtt.Client(client_id="test_reception", clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        # Connect to broker
        print(f"🔗 Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        
        # Start the loop
        client.loop_start()
        
        # Wait a moment for connection
        time.sleep(2)
        
        # Send a test message
        test_data = {
            "device_id": "test_device",
            "timestamp": datetime.utcnow().isoformat(),
            "displacement": 10.5,
            "force": 25.3,
            "message_id": 1,
            "publisher": "test_reception"
        }
        
        payload = json.dumps(test_data)
        print(f"📤 Sending test message: {test_data}")
        
        result = client.publish(TOPIC, payload, qos=1)
        
        # Wait for message processing
        time.sleep(3)
        
        print("✅ Test completed")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    test_backend_reception()
