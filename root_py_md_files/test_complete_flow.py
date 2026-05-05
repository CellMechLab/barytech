#!/usr/bin/env python3
"""
Test Complete Flow
Test the complete flow from MQTT publisher to frontend
"""

import paho.mqtt.client as mqtt
import json
import time
import requests
from datetime import datetime

# Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPIC = "device_data"
BACKEND_URL = "http://localhost:8000"

def test_complete_flow():
    """Test the complete flow"""
    print("=" * 60)
    print("🧪 Complete Flow Test")
    print("=" * 60)
    
    print("📋 Test Steps:")
    print("1. ✅ Backend is running")
    print("2. 📤 Send MQTT message")
    print("3. 🔄 Backend processes message")
    print("4. 📡 Backend broadcasts to WebSocket")
    print("5. 🌐 Frontend receives data")
    print("=" * 60)
    
    # Step 1: Check backend
    try:
        response = requests.get(f"{BACKEND_URL}/docs", timeout=5)
        if response.status_code == 200:
            print("✅ Step 1: Backend is running")
        else:
            print(f"❌ Step 1: Backend returned status {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Step 1: Backend is not accessible: {e}")
        return
    
    # Step 2: Send MQTT message
    print("\n📤 Step 2: Sending MQTT message...")
    
    client = mqtt.Client(client_id="test_flow", clean_session=True)
    
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("✅ Connected to MQTT broker")
            client.subscribe(TOPIC, qos=1)
        else:
            print(f"❌ Connection failed: {rc}")
    
    def on_message(client, userdata, msg):
        print(f"📨 Received message on topic {msg.topic}")
        try:
            data = json.loads(msg.payload.decode())
            print(f"📊 Message data: {data}")
        except Exception as e:
            print(f"❌ Error parsing message: {e}")
    
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
            "displacement": 20.5,
            "force": 51.3,
            "message_id": 1000,
            "publisher": "test_flow"
        }
        
        payload = json.dumps(test_data)
        print(f"📤 Sending: {test_data}")
        
        result = client.publish(TOPIC, payload, qos=1)
        
        print("✅ Step 2: MQTT message sent")
        
        # Wait for processing
        time.sleep(3)
        
        print("\n📋 Next Steps:")
        print("1. Open frontend-1.html in browser")
        print("2. Click 'Start Data Stream'")
        print("3. Run frontend1_publisher.py")
        print("4. Check if data appears in the frontend")
        print("\n🔍 Debugging:")
        print("- Check backend logs for 'Processing batch of X raw messages'")
        print("- Check backend logs for 'Checking websockets for client_id'")
        print("- Check browser console for WebSocket messages")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    test_complete_flow()
