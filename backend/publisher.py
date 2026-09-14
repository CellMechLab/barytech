import time
import math
import paho.mqtt.client as mqtt
import orjson
from datetime import datetime
import sys
import random

# MQTT Broker settings
broker = "127.0.0.1"
port = 1883
topic = "MON"

def on_connect(client, userdata, flags, rc):
    print("Connected with result code:", rc)

# CLI argument validation.
# points_per_batch           — how many MQTT publishes to send per second (throttling).
# points_per_curve           — samples split between the indent (phase=0) and retract
#                              (phase=1) legs of a single curve (motor_working=1 throughout).
# num_curves                 — how many full curves to simulate back-to-back (default 1).
# idle_points_between_curves — motor_working=0 samples sent after each curve to trigger
#                              the backend's 1->0 "motor stopped" curve-flush boundary
#                              (default 20). Set to 0 to reproduce the old behaviour
#                              (motor_working stays 1 forever, so the curve never flushes
#                              on its own — only via the backend's stuck-motor safety valve).
# delay_points_per_curve     — samples sent between indent and retract with phase=2
#                              (delay/dwell hold) and motor_working still 1, imitating the
#                              real device's hold period (default 20). Set to 0 to skip the
#                              delay leg entirely and go straight from indent to retract.
if len(sys.argv) not in (3, 4, 5, 6):
    print(
        "Usage: python publisher.py <points_per_batch> <points_per_curve> "
        "[num_curves=1] [idle_points_between_curves=20] [delay_points_per_curve=20]"
    )
    sys.exit(1)

try:
    points_per_batch = int(sys.argv[1])
    points_per_curve = int(sys.argv[2])
    num_curves = int(sys.argv[3]) if len(sys.argv) >= 4 else 1
    idle_points_between_curves = int(sys.argv[4]) if len(sys.argv) >= 5 else 20
    delay_points_per_curve = int(sys.argv[5]) if len(sys.argv) >= 6 else 20
except ValueError:
    print("Error: arguments must be integers.")
    sys.exit(1)

if (
    points_per_batch <= 0
    or points_per_curve <= 0
    or num_curves <= 0
    or idle_points_between_curves < 0
    or delay_points_per_curve < 0
):
    print(
        "Error: points_per_batch, points_per_curve, num_curves must be positive; "
        "idle_points_between_curves and delay_points_per_curve must be >= 0."
    )
    sys.exit(1)

# MQTT client
client = mqtt.Client(client_id="publisher_device_id", protocol=mqtt.MQTTv311, clean_session=False)
client.on_connect = on_connect
client.connect(broker, port, 60)
client.loop_start()

# Running count of every message published so far, across all curves.
total_messages_sent = 0
# Index (within the current curve) at which phase switches from indent (0) to retract (1).
phase_switch_index = points_per_curve // 2

def generate_displacement_mm(index, curve_number):
    """Generate a per-curve displacement waveform in millimeters (MQTT source unit)."""
    # Base indent range stays near real-device magnitudes so units stay realistic.
    min_val = -0.0012168244889861554
    max_val = -0.00003203646967473276
    scale = (max_val - min_val) / 2
    # Shift and stretch each curve so Z visibly jumps when a new curve replaces the old one.
    offset = (max_val + min_val) / 2 - (curve_number - 1) * 0.0004
    frequency = curve_number
    return offset + scale * curve_number * math.sin(math.radians(index * frequency))

def generate_force_mN(index, curve_number):
    """Generate a per-curve force waveform in millinewtons (MQTT source unit)."""
    # Amplitude and DC offset both grow with curve_number so Force charts look obviously different.
    amplitude = 0.005 * curve_number
    dc_offset = 0.004 * (curve_number - 1)
    frequency = 2 + curve_number
    base = dc_offset + amplitude * math.sin(math.radians(index * frequency))
    noise = random.uniform(-0.0005, 0.0005)
    return base + noise

def publish_point(index, phase, motor_working, curve_number):
    """Build one telemetry payload matching the real device schema and publish it."""
    global total_messages_sent
    disp = generate_displacement_mm(index, curve_number)
    force = generate_force_mN(index, curve_number)
    timestamp = datetime.now().isoformat()

    payload = {
        "displacement": disp,
        "force": force,
        "timestamp": timestamp,
        "device_id": "Qz2f4BuKsdcW",
        "device_token": "2iUnGOCh0w63eOWG",
        "phase": phase,
        "motor_working": motor_working,
    }

    # Use retain=False for streaming telemetry
    client.publish(topic, orjson.dumps(payload), qos=1, retain=False)
    total_messages_sent += 1

def send_batched(num_points, phase_for_index, motor_working, label, curve_number):
    """
    Send num_points telemetry samples at ~points_per_batch/sec, all sharing the
    given motor_working flag. Mirrors one leg (moving or idle) of a real curve.
    """
    sent_in_run = 0
    while sent_in_run < num_points:
        start_time = time.time()
        messages_this_round = 0

        while messages_this_round < points_per_batch and sent_in_run < num_points:
            publish_point(sent_in_run, phase_for_index(sent_in_run), motor_working, curve_number)
            sent_in_run += 1
            messages_this_round += 1

        elapsed = time.time() - start_time
        time.sleep(max(0, 1 - elapsed))
        print(f"[{label}] Sent {messages_this_round} msgs this round, Total: {total_messages_sent}")

try:
    for curve_number in range(1, num_curves + 1):
        # Motor stays active (motor_working=1) across all three sub-phases below —
        # indent, delay/dwell hold, and retract — exactly like the real device. This
        # means the backend's message_processor never sees a 1->0 transition mid-curve,
        # so it correctly buffers the whole indent+delay+retract sequence as ONE curve.
        print(
            f"--- Curve {curve_number}/{num_curves}: motor_working=1, phase=0 (indent) "
            f"— force amplitude x{curve_number} ---"
        )
        send_batched(
            phase_switch_index,
            phase_for_index=lambda i: 0,
            motor_working=1,
            label=f"curve {curve_number} indent",
            curve_number=curve_number,
        )

        if delay_points_per_curve > 0:
            print(f"--- Curve {curve_number}/{num_curves}: motor_working=1, phase=2 (delay/dwell) ---")
            send_batched(
                delay_points_per_curve,
                phase_for_index=lambda i: 2,
                motor_working=1,
                label=f"curve {curve_number} delay",
                curve_number=curve_number,
            )

        print(f"--- Curve {curve_number}/{num_curves}: motor_working=1, phase=1 (retract) ---")
        send_batched(
            points_per_curve - phase_switch_index,
            phase_for_index=lambda i: 1,
            motor_working=1,
            label=f"curve {curve_number} retract",
            curve_number=curve_number,
        )

        if idle_points_between_curves > 0:
            # Motor stops -> this is the 1->0 transition the backend's
            # message_processor uses to flush the just-finished curve as ONE
            # WebSocket message instead of streaming it point by point.
            print(
                f"--- Curve {curve_number}/{num_curves}: motor_working=0 (idle) "
                f"— should trigger the backend to flush the completed curve ---"
            )
            send_batched(
                idle_points_between_curves,
                phase_for_index=lambda i: 1,
                motor_working=0,
                label=f"curve {curve_number} idle",
                curve_number=curve_number,
            )

    print("All messages sent. Flushing in-flight publishes...")

    # Give a moment for any in-flight QoS1 messages to complete
    time.sleep(0.5)

except KeyboardInterrupt:
    print("Stopped by user")

finally:
    client.loop_stop()
    client.disconnect()
    print("Program finished.")
    sys.exit(0)
