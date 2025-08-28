# Publisher Optimizations

This document explains the optimizations made to the MQTT publishers for better performance and scalability.

## 🚀 Optimizations Implemented

### 1. **Device-Specific Topics**
- **Before**: All devices published to `device_data` topic
- **After**: Each device publishes to `device_data/{device_id}` topic
- **Benefits**: 
  - Better message routing
  - Reduced topic congestion
  - Improved scalability
  - Device-specific filtering

### 2. **Device-to-Frontend Mapping**
- **Frontend-1 Publishers**: `frontend1_device` and `frontend1_high_perf_device` → Frontend-1 (client_id "1")
- **Frontend-2 Publishers**: `frontend2_device` and `frontend2_high_perf_device` → Frontend-2 (client_id "2")
- **Benefits**:
  - Isolated data streams for each frontend
  - No cross-contamination between frontends
  - Better testing and debugging
  - Scalable architecture for multiple frontends

### 3. **Frontend-1 High Performance Publisher (Renamed)**
- **Total Messages**: 100,000 messages
- **Target Rate**: 10,000 messages/second
- **Topic**: `device_data/frontend1_high_perf_device`
- **Target Frontend**: Frontend-1 (client_id "1")
- **Optimization**: Device-specific topic for better performance
- **Purpose**: High-performance stress testing for frontend-1

### 4. **Frontend-2 High Performance Publisher (New)**
- **Total Messages**: 100,000 messages
- **Target Rate**: 10,000 messages/second
- **Topic**: `device_data/frontend2_high_perf_device`
- **Target Frontend**: Frontend-2 (client_id "2")
- **Optimization**: Device-specific topic for better performance
- **Purpose**: High-performance stress testing for frontend-2

### 5. **Frontend-1 Publisher (Standard)**
- **Total Messages**: 1,000 messages
- **Target Rate**: 100 messages/second
- **Topic**: `device_data/frontend1_device`
- **Target Frontend**: Frontend-1 (client_id "1")
- **Optimization**: Device-specific topic for better performance

### 6. **Frontend-2 Publisher (Standard)**
- **Total Messages**: 1,000 messages
- **Target Rate**: 100 messages/second
- **Topic**: `device_data/frontend2_device`
- **Target Frontend**: Frontend-2 (client_id "2")
- **Optimization**: Device-specific topic for better performance

### 7. **Backend MQTT Client Updates**
- **Subscriptions**: 
  - `device_data` (base topic for backward compatibility)
  - `device_data/#` (all device-specific topics)
- **Benefits**: 
  - Receives messages from both old and new topic structure
  - Supports multiple devices simultaneously
  - Better message routing

## 📊 Topic Structure

### **New Device-Specific Topics:**
```
device_data/frontend1_device              # Frontend-1 standard data
device_data/frontend1_high_perf_device    # Frontend-1 high-performance data
device_data/frontend2_device              # Frontend-2 standard data
device_data/frontend2_high_perf_device    # Frontend-2 high-performance data
device_data/{any_device_id}               # Any other device
```

### **Device-to-Frontend Mapping:**
```python
device_to_frontend = {
    "frontend1_device": "1",              # → Frontend-1
    "frontend1_high_perf_device": "1",    # → Frontend-1
    "frontend2_device": "2",              # → Frontend-2
    "frontend2_high_perf_device": "2"     # → Frontend-2
}
```

### **Message Format:**
```json
{
  "device_id": "frontend2_high_perf_device",
  "timestamp": "2024-12-04T12:34:56.789Z",
  "displacement": 15.5,
  "force": 45.3,
  "message_id": 123,
  "publisher": "frontend2_high_perf_publisher"
}
```

## 🎯 Performance Benefits

### **1. Reduced Topic Congestion**
- Each device has its own topic
- No message mixing between devices
- Better message isolation

### **2. Improved Scalability**
- Can handle multiple devices efficiently
- Device-specific message processing
- Better resource utilization

### **3. Enhanced Message Routing**
- Backend routes messages by device to specific frontends
- Device-specific WebSocket broadcasting
- Better client-side filtering

### **4. Frontend Isolation**
- Each frontend receives only its designated device data
- No cross-contamination between frontends
- Better testing and debugging capabilities

### **5. Backward Compatibility**
- Still subscribes to base `device_data` topic
- Supports existing publishers
- Gradual migration path

## 🔧 Configuration

### **Frontend-1 Publisher (Standard):**
```python
device_id = "frontend1_device"
topic = "device_data/frontend1_device"
target_rate = 100  # msg/sec
total_messages = 1000
target_frontend = "1"  # Frontend-1
```

### **Frontend-1 High Performance Publisher:**
```python
device_id = "frontend1_high_perf_device"
topic = "device_data/frontend1_high_perf_device"
target_rate = 10000  # msg/sec
total_messages = 100000
batch_size = 1000  # Larger batches for better performance
target_frontend = "1"  # Frontend-1
```

### **Frontend-2 Publisher (Standard):**
```python
device_id = "frontend2_device"
topic = "device_data/frontend2_device"
target_rate = 100  # msg/sec
total_messages = 1000
target_frontend = "2"  # Frontend-2
```

### **Frontend-2 High Performance Publisher:**
```python
device_id = "frontend2_high_perf_device"
topic = "device_data/frontend2_high_perf_device"
target_rate = 10000  # msg/sec
total_messages = 100000
batch_size = 1000  # Larger batches for better performance
target_frontend = "2"  # Frontend-2
```

### **Backend MQTT Client:**
```python
# Subscriptions
client.subscribe("device_data", qos=1)      # Base topic
client.subscribe("device_data/#", qos=1)    # Device-specific topics

# Device-to-Frontend Mapping
device_to_frontend = {
    "frontend1_device": "1",
    "frontend1_high_perf_device": "1", 
    "frontend2_device": "2",
    "frontend2_high_perf_device": "2"
}
```

## 📈 Expected Performance Improvements

### **Message Throughput:**
- **Before**: ~1,900 msg/sec (limited by topic congestion)
- **After**: ~10,000+ msg/sec (device-specific topics)

### **Latency:**
- **Before**: Higher latency due to topic mixing
- **After**: Lower latency with device isolation

### **Scalability:**
- **Before**: Limited to single topic
- **After**: Unlimited device topics

### **Reliability:**
- **Before**: Message loss due to topic congestion
- **After**: Better message delivery with isolated topics

### **Frontend Isolation:**
- **Before**: All frontends received all device data
- **After**: Each frontend receives only its designated device data

## 🚀 Usage

### **Start Frontend-1 Publisher (Standard):**
```bash
backend/new_architecture/venv/Scripts/python.exe frontend1_publisher.py
```

### **Start Frontend-1 High Performance Publisher:**
```bash
backend/new_architecture/venv/Scripts/python.exe frontend1_high_performance_publisher.py
```

### **Start Frontend-2 Publisher (Standard):**
```bash
backend/new_architecture/venv/Scripts/python.exe frontend2_publisher.py
```

### **Start Frontend-2 High Performance Publisher:**
```bash
backend/new_architecture/venv/Scripts/python.exe frontend2_high_performance_publisher.py
```

### **Monitor Performance:**
- Check backend logs for message rates and device-to-frontend mapping
- Monitor frontend data point counters
- Verify WebSocket message delivery to correct frontends

## 📝 Publisher Comparison

| Publisher | Device ID | Topic | Rate | Messages | Target Frontend | Purpose |
|-----------|-----------|-------|------|----------|-----------------|---------|
| **frontend1_publisher** | `frontend1_device` | `device_data/frontend1_device` | 100/sec | 1,000 | Frontend-1 | Standard testing for frontend-1 |
| **frontend1_high_performance_publisher** | `frontend1_high_perf_device` | `device_data/frontend1_high_perf_device` | 10,000/sec | 100,000 | Frontend-1 | High-performance stress testing for frontend-1 |
| **frontend1_high_performance_optimized** | `frontend1_ultra_high_perf_device` | `device_data/frontend1_ultra_high_perf_device` | 10,000/sec | 100,000 | Frontend-1 | **Ultra-high-performance with QoS 0 and batching** |
| **frontend2_publisher** | `frontend2_device` | `device_data/frontend2_device` | 100/sec | 1,000 | Frontend-2 | Standard testing for frontend-2 |
| **frontend2_high_performance_publisher** | `frontend2_high_perf_device` | `device_data/frontend2_high_perf_device` | 10,000/sec | 100,000 | Frontend-2 | High-performance stress testing for frontend-2 |
| **frontend2_high_performance_optimized** | `frontend2_ultra_high_perf_device` | `device_data/frontend2_ultra_high_perf_device` | 10,000/sec | 100,000 | Frontend-2 | **Ultra-high-performance with QoS 0 and batching** |

## 📝 Notes

- **Backward Compatibility**: Existing publishers using `device_data` topic still work
- **Gradual Migration**: Can migrate existing publishers to device-specific topics
- **Performance Monitoring**: Backend logs show message rates, device processing, and frontend routing
- **Scalability**: System can now handle multiple high-performance devices simultaneously
- **Device Isolation**: Each frontend has its own device ID and topic for better testing
- **High-Performance Testing**: Both frontends now have dedicated high-performance publishers for stress testing
- **Frontend Isolation**: Each frontend receives only its designated device data, preventing cross-contamination
