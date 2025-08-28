#!/usr/bin/env python3
"""
Test Backend Processing
Test if the backend is processing messages and broadcasting to frontend
"""

import paho.mqtt.client as mqtt
import json
import time
import requests
from datetime import datetime

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPIC = "device_data"
BACKEND_URL = "http://localhost:8000"

def test_backend_health():
    """Test if backend is running"""
    try:
        response = requests.get(f"{BACKEND_URL}/docs", timeout=5)
        if response.status_code == 200:
            print("✅ Backend is running")
            return True
        else:
            print(f"❌ Backend returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Backend is not accessible: {e}")
        return False

def send_test_message():
    """Send a test message and check if backend processes it"""
    print("📤 Sending test message to backend...")
    
    # Create test client
    client = mqtt.Client(client_id="test_processing", clean_session=True)
    
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("✅ Connected to MQTT broker")
            client.subscribe(TOPIC, qos=1)
        else:
            print(f"❌ Connection failed: {rc}")
    
    def on_message(client, userdata, msg):
        print(f"📨 Received message on topic {msg.topic}")
    
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        time.sleep(2)
        
        # Send test message
        test_data = {
            "device_id": "frontend1_device",
            "timestamp": datetime.utcnow().isoformat(),
            "displacement": 15.7,
            "force": 39.2,
            "message_id": 999,
            "publisher": "test_processing"
        }
        
        payload = json.dumps(test_data)
        print(f"📤 Sending: {test_data}")
        
        result = client.publish(TOPIC, payload, qos=1)
        
        # Wait for processing
        time.sleep(5)
        
        print("✅ Test message sent")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        client.loop_stop()
        client.disconnect()

def main():
    """Main test function"""
    print("=" * 60)
    print("🧪 Backend Processing Test")
    print("=" * 60)
    
    # Test backend health
    if not test_backend_health():
        print("❌ Backend is not running. Please start it first.")
        return
    
    # Send test message
    send_test_message()
    
    print("\n📋 Next Steps:")
    print("1. Open frontend-1.html in browser")
    print("2. Click 'Start Data Stream'")
    print("3. Run frontend1_publisher.py")
    print("4. Check if data appears in the frontend")

if __name__ == "__main__":
    main()
