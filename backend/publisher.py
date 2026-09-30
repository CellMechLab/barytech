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

# CLI argument validation
# points_per_batch  — messages published per second
# total_points      — total messages to send (curves are streamed back-to-back)
# points_per_curve  — optional, samples per full curve (indent + retract), default 200
if len(sys.argv) not in (3, 4):
    print("Usage: python publisher.py <points_per_batch> <total_points> [points_per_curve=200]")
    sys.exit(1)

try:
    points_per_batch = int(sys.argv[1])
    total_points = int(sys.argv[2])
    points_per_curve = int(sys.argv[3]) if len(sys.argv) == 4 else 200
except ValueError:
    print("Error: arguments must be integers.")
    sys.exit(1)

if points_per_batch <= 0 or total_points <= 0 or points_per_curve < 2:
    print("Error: arguments must be positive integers (points_per_curve >= 2).")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Curve model — tuned to the "0.2 kPa hydrogel" reference plot:
#   depth 0 -> ~72 nm, force ~0.7 uN -> ~8.3 uN, power-law loading,
#   ~5% curve-to-curve CV, noise growing with depth, small kink ~8-10 nm.
# Internally nm / uN; published in SI (m / N), same as the original script.
# ---------------------------------------------------------------------------
DISPLACEMENT_SIGN = -1          # original script sent negative displacement; set 1 for positive
INCLUDE_RETRACT = True          # False -> only loading legs (exactly what the plot shows)

MAX_DEPTH_NM = 72.0
MAX_DEPTH_SD_NM = 2.0
BASELINE_FORCE_UN = 0.7
BASELINE_FORCE_SD_UN = 0.02
FORCE_AT_MAX_UN = 8.3
POWER_EXPONENT = 2.5            # F - F0 ~ d^n
CURVE_CV = 0.05                 # stiffness spread between curves

NOISE_FLOOR_UN = 0.02           # noise SD near contact
NOISE_AT_MAX_UN = 0.35          # noise SD at max depth
NOISE_EXPONENT = 3.0

CONTACT_BUMP_NM = 8.5
CONTACT_BUMP_WIDTH_NM = 1.5
CONTACT_BUMP_UN = 0.04

RESIDUAL_DEPTH_FRACTION = 0.15  # on retract, force is back to baseline at this depth fraction
UNLOAD_EXPONENT = 1.8

NM_TO_M = 1e-9
UN_TO_N = 1e-6
K_MEAN = (FORCE_AT_MAX_UN - BASELINE_FORCE_UN) / MAX_DEPTH_NM ** POWER_EXPONENT


def make_curve_params():
    return {
        "max_depth": max(1.0, random.gauss(MAX_DEPTH_NM, MAX_DEPTH_SD_NM)),
        "f0": random.gauss(BASELINE_FORCE_UN, BASELINE_FORCE_SD_UN),
        "k": K_MEAN * max(0.5, random.gauss(1.0, CURVE_CV)),
    }


def loading_force(d, p):
    bump = CONTACT_BUMP_UN * math.exp(-0.5 * ((d - CONTACT_BUMP_NM) / CONTACT_BUMP_WIDTH_NM) ** 2)
    return p["f0"] + p["k"] * max(d, 0.0) ** POWER_EXPONENT + bump


def unloading_force(d, p):
    d_max = p["max_depth"]
    d_res = RESIDUAL_DEPTH_FRACTION * d_max
    if d <= d_res:
        return p["f0"]
    f_peak = loading_force(d_max, p)
    return p["f0"] + (f_peak - p["f0"]) * ((d - d_res) / (d_max - d_res)) ** UNLOAD_EXPONENT


def noise(d, p):
    frac = min(1.0, max(d, 0.0) / p["max_depth"])
    sd = NOISE_FLOOR_UN + (NOISE_AT_MAX_UN - NOISE_FLOOR_UN) * frac ** NOISE_EXPONENT
    return random.gauss(0.0, sd)


def curve_samples():
    """One full curve as a list of (depth_nm, force_uN)."""
    p = make_curve_params()
    n_indent = points_per_curve // 2 if INCLUDE_RETRACT else points_per_curve
    n_retract = points_per_curve - n_indent if INCLUDE_RETRACT else 0

    out = []
    for i in range(n_indent):
        d = p["max_depth"] * i / max(1, n_indent - 1)
        out.append((d, loading_force(d, p) + noise(d, p)))
    for i in range(n_retract):
        d = p["max_depth"] * (1 - (i + 1) / n_retract)
        out.append((d, unloading_force(d, p) + noise(d, p)))
    return out


def sample_stream():
    """Endless stream of samples, one curve after another."""
    while True:
        yield from curve_samples()


# MQTT client
client = mqtt.Client(client_id="publisher_device_id", protocol=mqtt.MQTTv311, clean_session=False)
client.on_connect = on_connect
client.connect(broker, port, 60)
client.loop_start()

total_messages_sent = 0
samples = sample_stream()

try:
    # Loop only while we still have points to send
    while total_messages_sent < total_points:
        start_time = time.time()
        messages_sent = 0

        for _ in range(points_per_batch):
            if total_messages_sent >= total_points:
                break

            depth_nm, force_uN = next(samples)
            timestamp = datetime.now().isoformat()

            payload = {
                "displacement": DISPLACEMENT_SIGN * depth_nm * NM_TO_M,  # m
                "force": force_uN * UN_TO_N,                             # N
                "timestamp": timestamp,
                "device_id": "Qz2f4BuKsdcW",
                "device_token": "2iUnGOCh0w63eOWG",
            }

            # Use retain=False for streaming telemetry
            info = client.publish(topic, orjson.dumps(payload), qos=1, retain=False)
            # Optional: wait for QoS1 ack for each message (can be skipped for speed)
            # info.wait_for_publish()

            messages_sent += 1
            total_messages_sent += 1

        elapsed = time.time() - start_time
        time.sleep(max(0, 1 - elapsed))
        print(f"Sent {messages_sent} msgs this round, Total: {total_messages_sent}")

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