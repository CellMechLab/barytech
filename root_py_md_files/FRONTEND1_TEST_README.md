# Frontend-1 Testing Guide

This guide explains how to test the frontend-1.html with the dedicated publisher.

## 📁 Files Created

- `frontend1_publisher.py` - Dedicated MQTT publisher for frontend-1
- `test_frontend1.py` - Test script with dependency checks
- `frontend-1.html` - Frontend interface for real-time data visualization

## 🚀 Quick Start

### 1. Start the Backend
```bash
cd backend/new_architecture
venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Open Frontend-1
Open `frontend-1.html` in your browser and click "Start Data Stream"

### 3. Run the Publisher
```bash
# From the project root directory
backend/new_architecture/venv/Scripts/python.exe frontend1_publisher.py
```

## 📊 Publisher Configuration

The `frontend1_publisher.py` is configured with:
- **Device ID**: `frontend1_device`
- **Target Rate**: 100 messages/second
- **Total Messages**: 1000
- **Topic**: `device_data`
- **QoS**: 1 (at least once delivery)

## 🎯 What You Should See

### In the Publisher Console:
```
🚀 Frontend-1 Publisher
📊 Configuration:
   - Device ID: frontend1_device
   - Target Rate: 100 msg/sec
   - Total Messages: 1000
   - Topic: device_data
🚀 Starting data transmission...
📤 Sent 100/1000 messages (rate: 63.4 msg/sec)
...
📊 Frontend-1 Publisher Statistics:
   - Total Messages Sent: 1000
   - Total Time: 16.51 seconds
   - Average Rate: 60.6 msg/sec
```

### In Frontend-1 Browser:
- ✅ "Connected to Backend" status
- 📈 Real-time chart updating with displacement and force data
- 📊 Message counter increasing
- ⏱️ Connection timer running
- 🎨 Blue-themed interface with "🚀 Frontend-1" title

## 🔧 Customization

You can modify the publisher settings in `frontend1_publisher.py`:

```python
# Change these values in the Frontend1Publisher.__init__ method
self.target_rate = 100  # messages per second
self.total_messages = 1000  # total messages to send
self.device_id = "frontend1_device"  # device identifier
```

## 🧪 Advanced Testing

Use the test script for dependency checks:
```bash
backend/new_architecture/venv/Scripts/python.exe test_frontend1.py
```

This will:
- ✅ Check if paho-mqtt is installed
- ✅ Verify MQTT broker is running
- ✅ Provide step-by-step instructions
- 🚀 Run the publisher when ready

## 🔍 Troubleshooting

### Publisher won't start:
- Make sure MQTT broker (mosquitto) is running
- Check that paho-mqtt is installed in the virtual environment

### Frontend not receiving data:
- Verify backend is running on port 8000
- Check that frontend-1.html is connected (should show "Connected to Backend")
- Ensure the WebSocket connection is established

### Data not displaying:
- Check browser console for JavaScript errors
- Verify Chart.js is loading properly
- Check that the data format matches what the frontend expects

## 📈 Data Format

The publisher sends data in this format:
```json
{
  "device_id": "frontend1_device",
  "timestamp": "2024-12-04T12:34:56.789Z",
  "displacement": 15.234,
  "force": 38.567,
  "message_id": 123,
  "publisher": "frontend1_publisher"
}
```

## 🎉 Success Indicators

When everything is working correctly:
- ✅ Publisher shows "Connected to MQTT broker"
- ✅ Frontend shows "Connected to Backend"
- ✅ Real-time chart updates smoothly
- ✅ Message counter increases
- ✅ No errors in browser console or publisher output
