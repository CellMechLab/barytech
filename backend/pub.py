"""
MQTT curve publisher for local MON-topic testing.

Publishes synthetic indent/retract curves with motor_working boundaries so the
backend curve accumulator can flush each curve to the frontend WebSocket
(motor 0->1 starts a curve, 1->0 finishes and broadcasts it).
"""
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

# Default device credentials used by the local test publisher
DEVICE_ID = "TsmfTUI5FCAf"
DEVICE_TOKEN = "q23GeDPV02xybXxT"


def on_connect(client, userdata, flags, rc):
    # Confirm broker handshake so rate/connect issues are visible in the terminal
    print("Connected with result code:", rc)

# CLI argument validation
# points_per_batch  — messages published per second (rate limit)
# num_curves        — how many full curves to send (default 10)
# points_per_curve  — samples per full curve indent+retract (default 100)
if len(sys.argv) not in (1, 2, 3, 4):
    print("Usage: python pub.py [points_per_batch=50] [num_curves=10] [points_per_curve=100]")
    sys.exit(1)

try:
    # Messages published per second while streaming curve points
    points_per_batch = int(sys.argv[1]) if len(sys.argv) >= 2 else 50
    # Number of complete curves to publish before exiting
    num_curves = int(sys.argv[2]) if len(sys.argv) >= 3 else 10
    # Samples per curve (indent half + retract half when INCLUDE_RETRACT)
    points_per_curve = int(sys.argv[3]) if len(sys.argv) >= 4 else 100
except ValueError:
    print("Error: arguments must be integers.")
    sys.exit(1)

if points_per_batch <= 0 or num_curves <= 0 or points_per_curve < 2:
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
    # Randomize stiffness/depth slightly so successive curves are not identical
    return {
        "max_depth": max(1.0, random.gauss(MAX_DEPTH_NM, MAX_DEPTH_SD_NM)),
        "f0": random.gauss(BASELINE_FORCE_UN, BASELINE_FORCE_SD_UN),
        "k": K_MEAN * max(0.5, random.gauss(1.0, CURVE_CV)),
    }


def loading_force(d, p):
    # Power-law loading plus a small contact bump near CONTACT_BUMP_NM
    bump = CONTACT_BUMP_UN * math.exp(-0.5 * ((d - CONTACT_BUMP_NM) / CONTACT_BUMP_WIDTH_NM) ** 2)
    return p["f0"] + p["k"] * max(d, 0.0) ** POWER_EXPONENT + bump


def unloading_force(d, p):
    # Unloading path that returns to baseline force at residual depth
    d_max = p["max_depth"]
    d_res = RESIDUAL_DEPTH_FRACTION * d_max
    if d <= d_res:
        return p["f0"]
    f_peak = loading_force(d_max, p)
    return p["f0"] + (f_peak - p["f0"]) * ((d - d_res) / (d_max - d_res)) ** UNLOAD_EXPONENT


def noise(d, p):
    # Depth-dependent force noise (larger SD near max depth)
    frac = min(1.0, max(d, 0.0) / p["max_depth"])
    sd = NOISE_FLOOR_UN + (NOISE_AT_MAX_UN - NOISE_FLOOR_UN) * frac ** NOISE_EXPONENT
    return random.gauss(0.0, sd)


def curve_samples():
    """
    One full curve as a list of (depth_nm, force_uN, phase, motor_working).

    All motion samples use motor_working=1. Callers must publish a trailing
    idle sample (motor_working=0) after this list so the backend flushes.
    phase: 0 = indent, 1 = retract.
    """
    p = make_curve_params()
    n_indent = points_per_curve // 2 if INCLUDE_RETRACT else points_per_curve
    n_retract = points_per_curve - n_indent if INCLUDE_RETRACT else 0

    out = []
    for i in range(n_indent):
        d = p["max_depth"] * i / max(1, n_indent - 1)
        out.append((d, loading_force(d, p) + noise(d, p), 0, 1))
    for i in range(n_retract):
        d = p["max_depth"] * (1 - (i + 1) / n_retract)
        out.append((d, unloading_force(d, p) + noise(d, p), 1, 1))
    return out


def build_payload(depth_nm, force_uN, phase, motor_working):
    # Build one MQTT telemetry dict in the shape the backend normalizer expects
    return {
        "displacement": DISPLACEMENT_SIGN * depth_nm * NM_TO_M,  # m
        "force": force_uN * UN_TO_N,                             # N
        "timestamp": datetime.now().isoformat(),
        "device_id": DEVICE_ID,
        "device_token": DEVICE_TOKEN,
        "phase": phase,
        "motor_working": motor_working,
    }


# MQTT client
client = mqtt.Client(client_id="publisher_device_id", protocol=mqtt.MQTTv311, clean_session=False)
client.on_connect = on_connect
client.connect(broker, port, 60)
client.loop_start()

# Counts total MQTT publishes across all curves (motion + idle flush points)
total_messages_sent = 0
# Counts how many complete curves (including their idle flush) have been finished
curves_completed = 0
# Holds points waiting to be rate-limited into the next one-second window
pending_payloads = []

print(
    f"Publishing {num_curves} curves x {points_per_curve} points "
    f"(+1 idle flush each) at ~{points_per_batch} msg/s"
)

try:
    for curve_index in range(num_curves):
        # Motion samples for this curve (motor_working=1 throughout)
        samples = curve_samples()
        for depth_nm, force_uN, phase, motor_working in samples:
            pending_payloads.append(build_payload(depth_nm, force_uN, phase, motor_working))

        # Trailing idle point: motor 1->0 edge that tells the backend to flush
        last_depth_nm, last_force_uN, last_phase, _ = samples[-1]
        pending_payloads.append(
            build_payload(last_depth_nm, last_force_uN, last_phase, 0)
        )

        # Drain pending payloads at points_per_batch messages per second
        while pending_payloads:
            start_time = time.time()
            messages_sent = 0
            for _ in range(points_per_batch):
                if not pending_payloads:
                    break
                payload = pending_payloads.pop(0)
                client.publish(topic, orjson.dumps(payload), qos=1, retain=False)
                messages_sent += 1
                total_messages_sent += 1

            elapsed = time.time() - start_time
            time.sleep(max(0, 1 - elapsed))
            print(
                f"Curve {curve_index + 1}/{num_curves}: "
                f"sent {messages_sent} msgs this round, Total: {total_messages_sent}"
            )

        curves_completed += 1
        print(f"Finished curve {curves_completed}/{num_curves} (motor_working flushed to 0)")

    print("All curves sent. Flushing in-flight publishes...")
    time.sleep(0.5)

except KeyboardInterrupt:
    print("Stopped by user")

finally:
    client.loop_stop()
    client.disconnect()
    print(
        f"Program finished. Curves={curves_completed}/{num_curves}, "
        f"messages={total_messages_sent}"
    )
    sys.exit(0)
