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
#                              (default 20). Set to 0 to reproduce the old behaviour.
# delay_points_per_curve     — samples sent between indent and retract with phase=2
#                              (delay/dwell hold) and motor_working still 1 (default 20).
#                              Set to 0 to skip the delay leg.
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

# ---------------------------------------------------------------------------
# Curve model — tuned to the "0.2 kPa hydrogel" reference plot:
#   depth 0 -> ~72 nm, force ~0.7 uN -> ~8.3 uN, power-law loading,
#   ~5% curve-to-curve CV, noise growing with depth, small contact bump ~8-10 nm.
# Internally everything is in nm / uN; converted to mm / mN (MQTT source units)
# only when publishing.
# ---------------------------------------------------------------------------
DISPLACEMENT_SIGN = -1          # device reports indentation as negative mm; set 1 for positive

MAX_DEPTH_NM = 72.0             # mean max indentation depth
MAX_DEPTH_SD_NM = 2.0           # curve-to-curve spread of max depth
BASELINE_FORCE_UN = 0.7         # force at contact (d = 0)
BASELINE_FORCE_SD_UN = 0.02
FORCE_AT_MAX_UN = 8.3           # mean force at MAX_DEPTH_NM
POWER_EXPONENT = 2.5            # F - F0 ~ d^n (fitted to the plot's shape)
CURVE_CV = 0.05                 # stiffness spread between curves (~5% CV)

NOISE_FLOOR_UN = 0.02           # noise SD near contact
NOISE_AT_MAX_UN = 0.35          # noise SD at max depth
NOISE_EXPONENT = 3.0            # how sharply noise grows with depth

CONTACT_BUMP_NM = 8.5           # small kink seen around 8-10 nm
CONTACT_BUMP_WIDTH_NM = 1.5
CONTACT_BUMP_UN = 0.04

RELAXATION_FRACTION = 0.06      # force drop during dwell (viscoelastic relaxation)
RELAXATION_TAU_FRACTION = 0.3   # relaxation time constant as fraction of dwell length
RESIDUAL_DEPTH_FRACTION = 0.15  # on retract, force returns to baseline at this depth fraction
UNLOAD_EXPONENT = 1.8

NM_TO_MM = 1e-6
UN_TO_MN = 1e-3
K_MEAN = (FORCE_AT_MAX_UN - BASELINE_FORCE_UN) / MAX_DEPTH_NM ** POWER_EXPONENT


def make_curve_params():
    """Random per-curve parameters so repeated curves scatter like real measurements."""
    return {
        "max_depth": max(1.0, random.gauss(MAX_DEPTH_NM, MAX_DEPTH_SD_NM)),
        "f0": random.gauss(BASELINE_FORCE_UN, BASELINE_FORCE_SD_UN),
        "k": K_MEAN * max(0.5, random.gauss(1.0, CURVE_CV)),
    }


def loading_force(d, p):
    """Noise-free loading force (uN) at depth d (nm)."""
    bump = CONTACT_BUMP_UN * math.exp(-0.5 * ((d - CONTACT_BUMP_NM) / CONTACT_BUMP_WIDTH_NM) ** 2)
    return p["f0"] + p["k"] * max(d, 0.0) ** POWER_EXPONENT + bump


def noise(d, p):
    frac = min(1.0, max(d, 0.0) / p["max_depth"])
    sd = NOISE_FLOOR_UN + (NOISE_AT_MAX_UN - NOISE_FLOOR_UN) * frac ** NOISE_EXPONENT
    return random.gauss(0.0, sd)


def ramp(n, start, end):
    if n <= 0:
        return []
    if n == 1:
        return [end]
    return [start + (end - start) * i / (n - 1) for i in range(n)]


def indent_samples(n, p):
    return [(d, loading_force(d, p) + noise(d, p)) for d in ramp(n, 0.0, p["max_depth"])]


def delay_samples(n, p):
    d = p["max_depth"]
    f_peak = loading_force(d, p)
    drop = RELAXATION_FRACTION * (f_peak - p["f0"])
    tau = max(1.0, RELAXATION_TAU_FRACTION * n)
    return [(d, f_peak - drop * (1 - math.exp(-i / tau)) + noise(d, p)) for i in range(n)]


def relaxed_peak(p, had_delay):
    f_peak = loading_force(p["max_depth"], p)
    if not had_delay:
        return f_peak
    tau = max(1.0, RELAXATION_TAU_FRACTION * delay_points_per_curve)
    return f_peak - RELAXATION_FRACTION * (f_peak - p["f0"]) * (1 - math.exp(-delay_points_per_curve / tau))


def retract_samples(n, p, had_delay):
    d_max = p["max_depth"]
    d_res = RESIDUAL_DEPTH_FRACTION * d_max
    f_start = relaxed_peak(p, had_delay)
    out = []
    for d in ramp(n, d_max, 0.0):
        if d <= d_res:
            f = p["f0"]
        else:
            f = p["f0"] + (f_start - p["f0"]) * ((d - d_res) / (d_max - d_res)) ** UNLOAD_EXPONENT
        out.append((d, f + noise(d, p)))
    return out


def idle_samples(n, p):
    return [(0.0, p["f0"] + noise(0.0, p)) for _ in range(n)]


# MQTT client
client = mqtt.Client(client_id="publisher_device_id", protocol=mqtt.MQTTv311, clean_session=False)
client.on_connect = on_connect
client.connect(broker, port, 60)
client.loop_start()

total_messages_sent = 0
phase_switch_index = points_per_curve // 2


def publish_point(depth_nm, force_uN, phase, motor_working):
    """Build one telemetry payload matching the real device schema and publish it."""
    global total_messages_sent
    payload = {
        "displacement": DISPLACEMENT_SIGN * depth_nm * NM_TO_MM,  # mm
        "force": force_uN * UN_TO_MN,                             # mN
        "timestamp": datetime.now().isoformat(),
        "device_id": "Qz2f4BuKsdcW",
        "device_token": "2iUnGOCh0w63eOWG",
        "phase": phase,
        "motor_working": motor_working,
    }
    client.publish(topic, orjson.dumps(payload), qos=1, retain=False)
    total_messages_sent += 1


def send_batched(samples, phase, motor_working, label):
    """Send (depth_nm, force_uN) samples at ~points_per_batch/sec."""
    i = 0
    while i < len(samples):
        start_time = time.time()
        sent_this_round = 0
        while sent_this_round < points_per_batch and i < len(samples):
            d, f = samples[i]
            publish_point(d, f, phase, motor_working)
            i += 1
            sent_this_round += 1
        time.sleep(max(0, 1 - (time.time() - start_time)))
        print(f"[{label}] Sent {sent_this_round} msgs this round, Total: {total_messages_sent}")


try:
    for curve_number in range(1, num_curves + 1):
        p = make_curve_params()
        print(
            f"--- Curve {curve_number}/{num_curves}: max depth {p['max_depth']:.1f} nm, "
            f"stiffness x{p['k'] / K_MEAN:.3f} ---"
        )

        # motor_working=1 across indent, delay and retract, like the real device,
        # so the backend buffers the whole sequence as ONE curve.
        send_batched(indent_samples(phase_switch_index, p), 0, 1, f"curve {curve_number} indent")

        had_delay = delay_points_per_curve > 0
        if had_delay:
            send_batched(delay_samples(delay_points_per_curve, p), 2, 1, f"curve {curve_number} delay")

        send_batched(
            retract_samples(points_per_curve - phase_switch_index, p, had_delay),
            1, 1, f"curve {curve_number} retract",
        )

        if idle_points_between_curves > 0:
            # 1->0 transition: backend flushes the completed curve.
            send_batched(idle_samples(idle_points_between_curves, p), 1, 0, f"curve {curve_number} idle")

    print("All messages sent. Flushing in-flight publishes...")
    time.sleep(0.5)

except KeyboardInterrupt:
    print("Stopped by user")

finally:
    client.loop_stop()
    client.disconnect()
    print("Program finished.")
    sys.exit(0)