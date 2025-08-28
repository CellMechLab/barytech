# Frontend-2 High Performance Publisher

This is a high-performance MQTT publisher designed to stress test the system with 10,000 messages per second for 100,000 total messages.

## 📁 Files Created

- `frontend2_high_performance_publisher.py` - High-performance MQTT publisher
- `test_high_performance_publisher.py` - Test script with system checks
- `frontend-2.html` - Frontend interface for real-time data visualization

## 🚀 Quick Start

### 1. Start the Backend
```bash
cd backend/new_architecture
venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Open Frontend-2
Open `frontend-2.html` in your browser and click "Start Data Stream"

### 3. Run the High-Performance Publisher
```bash
# From the project root directory
backend/new_architecture/venv/Scripts/python.exe frontend2_high_performance_publisher.py
```

## 📊 Publisher Configuration

The `frontend2_high_performance_publisher.py` is configured with:
- **Device ID**: `frontend2_high_perf_device`
- **Target Rate**: 10,000 messages/second
- **Total Messages**: 100,000
- **Batch Size**: 100 messages per batch
- **Topic**: `device_data`
- **QoS**: 1 (at least once delivery)

## 🎯 Performance Results

### Actual Performance (from test run):
- **Total Messages Sent**: 92,281
- **Total Time**: 48.29 seconds
- **Average Rate**: 1,909 msg/sec
- **Target Rate**: 10,000 msg/sec
- **Performance**: 19.1% of target

### Performance Notes:
- The actual rate of ~1,900 msg/sec is still very high and demonstrates system capability
- Performance is limited by:
  - MQTT broker processing speed
  - Network bandwidth
  - System resources (CPU, memory)
  - Python threading limitations

## 🔧 Customization

You can modify the publisher settings in `frontend2_high_performance_publisher.py`:

```python
# Change these values in the HighPerformancePublisher.__init__ method
self.target_rate = 10000  # messages per second
self.total_messages = 100000  # total messages to send
self.batch_size = 100  # messages per batch
self.device_id = "frontend2_high_perf_device"  # device identifier
```

## 🧪 Advanced Testing

Use the test script for system checks:
```bash
backend/new_architecture/venv/Scripts/python.exe test_high_performance_publisher.py
```

This will:
- ✅ Check system resources (CPU, memory, disk)
- ✅ Verify MQTT broker is running
- ✅ Confirm backend is accessible
- ✅ Provide performance recommendations
- 🚀 Run the high-performance publisher when ready

## 🎯 What You Should See

### In the Publisher Console:
```
🚀 Frontend-2 High Performance Publisher
📊 Configuration:
   - Device ID: frontend2_high_perf_device
   - Target Rate: 10,000 msg/sec
   - Total Messages: 100,000
   - Batch Size: 100
   - Topic: device_data
🚀 Starting high-performance data transmission...
📤 Progress: 1,801/100,000 (1.8%) - Rate: 1,800 msg/sec
📤 Progress: 3,701/100,000 (3.7%) - Rate: 1,818 msg/sec
...
📊 Frontend-2 High Performance Publisher Statistics:
   - Total Messages Sent: 92,281
   - Total Time: 48.29 seconds
   - Average Rate: 1,909 msg/sec
   - Target Rate: 10,000 msg/sec
   - Performance: 19.1% of target
```

### In Frontend-2 Browser:
- ✅ "Connected to Backend" status
- 📈 Real-time chart updating rapidly with displacement and force data
- 📊 Message counter increasing rapidly
- ⏱️ Connection timer running
- 🎨 Red-themed interface with "🔥 Frontend-2" title

## 🔍 Troubleshooting

### Publisher performance is low:
- Check system resources (CPU, memory)
- Verify MQTT broker configuration
- Consider reducing target rate or batch size
- Monitor network bandwidth

### Frontend not receiving data:
- Verify backend is running on port 8000
- Check that frontend-2.html is connected
- Ensure WebSocket connection is established
- Monitor backend logs for processing messages

### System becomes unresponsive:
- Stop the publisher (Ctrl+C)
- Check system resource usage
- Restart the backend if necessary
- Consider running with lower message rates

## 📈 Data Format

The publisher sends data in this format:
```json
{
  "device_id": "frontend2_high_perf_device",
  "timestamp": "2024-12-04T12:34:56.789Z",
  "displacement": 7.234,
  "force": 21.567,
  "message_id": 12345,
  "publisher": "frontend2_high_perf_publisher",
  "batch_id": 123
}
```

## 🎉 Success Indicators

When everything is working correctly:
- ✅ Publisher shows "Connected to MQTT broker"
- ✅ Frontend shows "Connected to Backend"
- ✅ Real-time chart updates rapidly
- ✅ Message counter increases quickly
- ✅ System remains responsive
- ✅ No errors in browser console or publisher output

## ⚡ Performance Optimization Tips

1. **System Resources**: Ensure adequate CPU and memory
2. **Network**: Use localhost for best performance
3. **MQTT Broker**: Configure for high throughput
4. **Backend**: Monitor processing pipeline
5. **Frontend**: Use efficient chart updates

## 🔄 Comparison with Frontend-1 Publisher

| Feature | Frontend-1 | Frontend-2 High-Performance |
|---------|------------|---------------------------|
| Target Rate | 100 msg/sec | 10,000 msg/sec |
| Total Messages | 1,000 | 100,000 |
| Expected Duration | ~10 seconds | ~10 seconds |
| Use Case | Normal testing | Stress testing |
| Performance | ~60 msg/sec | ~1,900 msg/sec |
