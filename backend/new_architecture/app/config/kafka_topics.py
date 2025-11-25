"""
Kafka Topic Configuration
Defines fixed topic mapping for simplified two-topic setup
"""

# Fixed topic configuration - only two topics
FIXED_TOPICS = {
    "frontend1_ultra_high_perf_device": "iot-device-frontend1_ultra_high_perf_device",
    "frontend2_ultra_high_perf_device": "iot-device-frontend2_ultra_high_perf_device",
    # 👇 Add this line
    "frontend1_high_perf_device": "iot-device-frontend1_ultra_high_perf_device",
}


def get_topic_for_device(device_id: str) -> str:
    """
    Get the Kafka topic for a specific device.
    Returns the fixed topic if device is configured, otherwise raises an error.
    """
    if device_id in FIXED_TOPICS:
        return FIXED_TOPICS[device_id]
    else:
        raise ValueError(
            f"Device '{device_id}' is not configured. Available devices: {list(FIXED_TOPICS.keys())}"
        )


def get_all_topics() -> list:
    """Get list of all configured topics"""
    return list(FIXED_TOPICS.values())


def get_all_device_ids() -> list:
    """Get list of all configured device IDs"""
    return list(FIXED_TOPICS.keys())


def is_device_configured(device_id: str) -> bool:
    """Check if a device is configured for Kafka topics"""
    return device_id in FIXED_TOPICS

