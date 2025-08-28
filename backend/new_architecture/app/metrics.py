"""
Prometheus Metrics for MQTT System Monitoring

This module provides comprehensive metrics for monitoring the entire MQTT pipeline:
- Publisher → Broker → Subscriber → Processor → DB/WebSocket
"""

try:
    from prometheus_client import Counter, Gauge, Histogram, Summary
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    print("Warning: prometheus_client not available, metrics will be disabled")
    PROMETHEUS_AVAILABLE = False

from fastapi import APIRouter, Response
import time

router = APIRouter()

# Initialize metrics only if prometheus_client is available
if PROMETHEUS_AVAILABLE:
    # MQTT Layer Metrics
    MQTT_RECEIVED = Counter("mqtt_messages_received_total", "MQTT messages received by backend")
    MQTT_PARSE_ERRORS = Counter("mqtt_parse_errors_total", "JSON parse errors in MQTT messages")
    MQTT_PARSE_SUCCESS = Counter("mqtt_parse_success_total", "Successfully parsed MQTT messages")
    MQTT_CONNECTION_STATUS = Gauge("mqtt_connection_status", "MQTT connection status (1=connected, 0=disconnected)")
    
    # Queue Metrics
    INGRESS_QUEUE_LEN = Gauge("ingress_queue_length", "Raw ingress queue size")
    DEVICE_QUEUE_LEN = Gauge("device_queue_length", "Per-device queue size", ["device_id"])
    SAVE_QUEUE_LEN = Gauge("save_queue_length", "Per-device save queue size", ["device_id"])
    
    # Processing Metrics
    BATCH_SIZE_PROC = Histogram("processor_batch_size", "Processor batch size", buckets=[10, 50, 100, 200, 500, 1000, 2000])
    PROC_LAT_SEC = Summary("processor_latency_seconds", "Processor latency per batch")
    DEVICE_PROCESSED = Counter("device_messages_processed_total", "Messages processed per device", ["device_id"])
    PROCESSING_ERRORS = Counter("processing_errors_total", "Processing errors", ["stage"])
    
    # Database Metrics
    DB_BATCH_WRITES = Counter("db_batch_writes_total", "DB batch writes")
    DB_WRITE_LAT_SEC = Summary("db_write_latency_seconds", "DB write latency")
    DB_WRITE_ERRORS = Counter("db_write_errors_total", "DB write errors")
    DB_SAVE_QUEUE_FULL = Counter("db_save_queue_full_total", "DB save queue full events")
    
    # WebSocket Metrics
    WS_CONNECTIONS = Gauge("ws_connections", "Active WS connections", ["client_id"])
    WS_SEND_BATCH = Histogram("ws_send_batch_size", "WS batch size", buckets=[50, 100, 200, 500, 1000, 2000])
    WS_SEND_ERRORS = Counter("ws_send_errors_total", "WS send errors")
    WS_SEND_SUCCESS = Counter("ws_send_success_total", "WS send success", ["client_id"])
    WS_COMPRESSION_RATIO = Histogram("ws_compression_ratio", "WebSocket compression ratio", buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    
    # End-to-End Metrics
    E2E_LATENCY_SEC = Histogram("end_to_end_latency_seconds", "End-to-end latency", buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5])
    MESSAGE_LOSS = Counter("message_loss_total", "Message loss by stage", ["stage"])
    
    # System Health Metrics
    SYSTEM_UPTIME = Gauge("system_uptime_seconds", "System uptime in seconds")
    ACTIVE_DEVICES = Gauge("active_devices", "Number of active devices")
    TOTAL_MESSAGES_SENT = Counter("total_messages_sent_to_frontend", "Total messages sent to frontend")
    
    # Performance Metrics
    MQTT_RATE = Gauge("mqtt_message_rate", "MQTT messages per second")
    PROCESSING_RATE = Gauge("processing_rate", "Messages processed per second")
    BROADCAST_RATE = Gauge("broadcast_rate", "Messages broadcast per second")
    DB_RATE = Gauge("db_write_rate", "Database writes per second")
    
    # Custom metrics for our specific use case
    BATCHED_MESSAGES = Counter("batched_messages_total", "Batched messages received", ["batch_size"])
    SINGLE_MESSAGES = Counter("single_messages_total", "Single messages received")
    DEVICE_MAPPING_HITS = Counter("device_mapping_hits", "Device to frontend mapping hits", ["device_id", "frontend_id"])

@router.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    if PROMETHEUS_AVAILABLE:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
    else:
        return Response("# Prometheus metrics disabled - prometheus_client not available", media_type="text/plain")

# Utility functions for updating metrics
def update_queue_metrics():
    """Update queue length metrics."""
    if not PROMETHEUS_AVAILABLE:
        return
        
    try:
        from app.message_processor import device_queues, device_save_queues
        from app.mqtt_client import message_queue
        
        # Update ingress queue length
        INGRESS_QUEUE_LEN.set(message_queue.qsize())
        
        # Update device queue lengths
        for device_id, queue in device_queues.items():
            DEVICE_QUEUE_LEN.labels(device_id=device_id).set(queue.qsize())
        
        # Update save queue lengths
        for device_id, queue in device_save_queues.items():
            SAVE_QUEUE_LEN.labels(device_id=device_id).set(queue.qsize())
    except Exception as e:
        print(f"Error updating queue metrics: {e}")

def update_websocket_metrics():
    """Update WebSocket connection metrics."""
    if not PROMETHEUS_AVAILABLE:
        return
        
    try:
        from app.websocket_manager import websocket_connections
        
        # Reset all connection counts
        for client_id in ["1", "2"]:
            WS_CONNECTIONS.labels(client_id=client_id).set(0)
        
        # Update with current connections
        for client_id, connections in websocket_connections.items():
            WS_CONNECTIONS.labels(client_id=client_id).set(len(connections))
    except Exception as e:
        print(f"Error updating WebSocket metrics: {e}")

def record_e2e_latency(start_time):
    """Record end-to-end latency for a message."""
    if not PROMETHEUS_AVAILABLE:
        return
        
    try:
        latency = time.time() - start_time
        E2E_LATENCY_SEC.observe(latency)
    except Exception as e:
        print(f"Error recording E2E latency: {e}")

def record_batch_processing(batch_size, processing_time):
    """Record batch processing metrics."""
    if not PROMETHEUS_AVAILABLE:
        return
        
    try:
        BATCH_SIZE_PROC.observe(batch_size)
        PROC_LAT_SEC.observe(processing_time)
    except Exception as e:
        print(f"Error recording batch processing metrics: {e}")

def record_websocket_send(batch_size, client_id, success=True, compression_ratio=None):
    """Record WebSocket send metrics."""
    if not PROMETHEUS_AVAILABLE:
        return
        
    try:
        WS_SEND_BATCH.observe(batch_size)
        
        if success:
            WS_SEND_SUCCESS.labels(client_id=client_id).inc()
        else:
            WS_SEND_ERRORS.inc()
        
        if compression_ratio is not None:
            WS_COMPRESSION_RATIO.observe(compression_ratio)
    except Exception as e:
        print(f"Error recording WebSocket send metrics: {e}")

def record_message_loss(stage, count=1):
    """Record message loss at a specific stage."""
    if not PROMETHEUS_AVAILABLE:
        return
        
    try:
        MESSAGE_LOSS.labels(stage=stage).inc(count)
    except Exception as e:
        print(f"Error recording message loss: {e}")

def record_device_processing(device_id, count=1):
    """Record device processing metrics."""
    if not PROMETHEUS_AVAILABLE:
        return
        
    try:
        DEVICE_PROCESSED.labels(device_id=device_id).inc(count)
    except Exception as e:
        print(f"Error recording device processing metrics: {e}")

def record_db_operation(success=True, batch_size=1, latency=None):
    """Record database operation metrics."""
    if not PROMETHEUS_AVAILABLE:
        return
        
    try:
        if success:
            DB_BATCH_WRITES.inc()
            if latency is not None:
                DB_WRITE_LAT_SEC.observe(latency)
        else:
            DB_WRITE_ERRORS.inc()
    except Exception as e:
        print(f"Error recording DB operation metrics: {e}")

def record_mqtt_message(parsed_successfully=True):
    """Record MQTT message metrics."""
    if not PROMETHEUS_AVAILABLE:
        return
        
    try:
        MQTT_RECEIVED.inc()
        if parsed_successfully:
            MQTT_PARSE_SUCCESS.inc()
        else:
            MQTT_PARSE_ERRORS.inc()
    except Exception as e:
        print(f"Error recording MQTT message metrics: {e}")

def record_message_type(is_batched, batch_size=None):
    """Record message type metrics."""
    if not PROMETHEUS_AVAILABLE:
        return
        
    try:
        if is_batched and batch_size:
            BATCHED_MESSAGES.labels(batch_size=batch_size).inc()
        else:
            SINGLE_MESSAGES.inc()
    except Exception as e:
        print(f"Error recording message type metrics: {e}")

def record_device_mapping(device_id, frontend_id):
    """Record device to frontend mapping."""
    if not PROMETHEUS_AVAILABLE:
        return
        
    try:
        DEVICE_MAPPING_HITS.labels(device_id=device_id, frontend_id=frontend_id).inc()
    except Exception as e:
        print(f"Error recording device mapping metrics: {e}")

# System health update function
def update_system_health():
    """Update system health metrics."""
    if not PROMETHEUS_AVAILABLE:
        return
        
    try:
        from app.message_processor import device_queues, total_messages_sent_to_frontend
        from app.mqtt_client import message_counters
        
        # Update uptime
        SYSTEM_UPTIME.set(time.time() - message_counters.start_time)
        
        # Update active devices
        ACTIVE_DEVICES.set(len(device_queues))
        
        # Update total messages sent
        TOTAL_MESSAGES_SENT._value._value = total_messages_sent_to_frontend
        
        # Update rates (calculate from counters)
        stats = message_counters.get_stats()
        MQTT_RATE.set(stats.get('mqtt_rate', 0))
        PROCESSING_RATE.set(stats.get('processing_rate', 0))
        BROADCAST_RATE.set(stats.get('broadcast_rate', 0))
        DB_RATE.set(stats.get('db_rate', 0))
        
        # Update queue metrics
        update_queue_metrics()
        
        # Update WebSocket metrics
        update_websocket_metrics()
    except Exception as e:
        print(f"Error updating system health metrics: {e}")
