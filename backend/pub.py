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

# CLI: python publisher.py <num_curves>
#   num_curves — how many complete indent(+retract) curves to publish
if len(sys.argv) != 2:
    print("Usage: python publisher.py <num_curves>")
    sys.exit(1)

try:
    num_curves = int(sys.argv[1])
except ValueError:
    print("Error: <num_curves> must be an integer.")
    sys.exit(1)

if num_curves <= 0:
    print("Error: <num_curves> must be a positive integer.")
    sys.exit(1)

# Publish rate (messages per second); one curve with retract is ~240 messages
PUBLISH_RATE_HZ = 50
CURVE_PAUSE_S = 1.0             # idle gap between curves

# ---------------------------------------------------------------------------
# Curve model — shape taken from processed_data_0.2kPa 1.csv (10 curves),
# rescaled to Z 0 -> ~30 um and force ~50 uN -> ~350 uN (force limit).
#   In the CSV, force rises slowly then steeply (convex, ~power law), then
#   flattens just before the limit; ~122 points per curve.
#   Noise: even/odd zigzag + random scatter, both growing with force.
# Internally um / uN; published as SI (m / N) x OUTPUT_SCALE, i.e. mm / mN.
# Displacement positive, force negative.
# ---------------------------------------------------------------------------
DISPLACEMENT_SIGN = 1           # positive displacement (set -1 if the backend expects negative)
FORCE_SIGN = -1                 # negative force (set 1 for positive)
OUTPUT_SCALE = 1e3              # published values x 10^3 (m -> mm, N -> mN)
INCLUDE_RETRACT = True          # False -> only indent legs (what the CSV contains)

Z_MAX_UM = 30.0                 # nominal depth reached at the force limit
F_START_UN = 50.0               # contact force at Z = 0
F_END_UN = 350.0                # force limit

# Normalized mean shape of the 10 reference curves:
# g = (F - F0) / (Fend - F0) at u = Z / Zmax = 0, 0.05, 0.10 ... 1.0
TEMPLATE_G = [
    0.0000, 0.0119, 0.0283, 0.0457, 0.0667, 0.0892, 0.1154, 0.1432, 0.1737,
    0.2072, 0.2446, 0.2865, 0.3324, 0.3846, 0.4412, 0.5083, 0.5862, 0.6749,
    0.7823, 0.9082, 0.9963,
]
TEMPLATE_DU = 1.0 / (len(TEMPLATE_G) - 1)
TAIL_SLOPE_G = 2.0              # extrapolation beyond u = 1 (normalized slope)

POINTS_PER_CURVE = 122          # as in the CSV
Z_STEP_UM = Z_MAX_UM / POINTS_PER_CURVE   # ~0.246 um
Z_STEP_SD_UM = 0.007
SKIP_PROB = 0.03                # occasional skipped sample (double step)

F0_SD_UN = 0.5                  # contact force spread between curves
SCALE_SD = 0.02                 # stiffness spread between curves

FORCE_STOP_UN = 341.0           # indent stops when the next point would exceed this ...
FORCE_STOP_SD_UN = 1.5
FINAL_FORCE_RANGE_UN = (341.0, 350.0)  # ... and a final point lands here, ~2 steps further
FINAL_STEP_UM = 2 * Z_STEP_UM

ZIGZAG_UN = (0.6, 5.0)          # alternating noise amplitude = a + b*g  (g = 0..1)
SCATTER_UN = (0.7, 2.5)         # gaussian noise SD           = a + b*g

RESIDUAL_DEPTH_FRACTION = 0.15  # retract: force back at baseline at this depth fraction
UNLOAD_EXPONENT = 1.8

UM_TO_M = 1e-6
UN_TO_N = 1e-6


def template_g(u):
    """Normalized reference shape g(u), linear interpolation."""
    if u <= 0:
        return TEMPLATE_G[0]
    pos = u / TEMPLATE_DU
    i = int(pos)
    if i >= len(TEMPLATE_G) - 1:
        return TEMPLATE_G[-1] + TAIL_SLOPE_G * (u - 1.0)
    t = pos - i
    return TEMPLATE_G[i] * (1 - t) + TEMPLATE_G[i + 1] * t


def make_curve_params():
    return {
        "f0_offset": random.gauss(0.0, F0_SD_UN),
        "scale": random.gauss(1.0, SCALE_SD),
        "stop": random.gauss(FORCE_STOP_UN, FORCE_STOP_SD_UN),
        "zig_phase": random.choice((-1, 1)),
    }


def clean_force(z, p):
    g = template_g(z / Z_MAX_UM)
    return F_START_UN + p["f0_offset"] + (F_END_UN - F_START_UN) * g * p["scale"]


def noisy(z, f, i, p):
    g = max(0.0, (f - F_START_UN) / (F_END_UN - F_START_UN))
    zig = (ZIGZAG_UN[0] + ZIGZAG_UN[1] * g) * p["zig_phase"] * (-1) ** i
    return f + zig + random.gauss(0.0, SCATTER_UN[0] + SCATTER_UN[1] * g)


def curve_samples():
    """One full curve as a list of sample dicts (motor=1 while moving).

    phase: 0 = indent, 1 = retract (matches mqtt_client / message_processor).
    motor: 1 for every live sample; the stream adds motor=0 after the curve
    so the backend can flush (message_processor 1->0 edge).
    """
    # Random stiffness / contact / stop params for this curve
    p = make_curve_params()
    # Accumulated (z_um, force_uN, phase) samples for this indent(+retract)
    out = []
    z, i = 0.0, 0
    while True:
        # Indent sample: phase 0, motor still moving
        out.append({
            "z_um": z,
            "force_uN": noisy(z, clean_force(z, p), i, p),
            "phase": 0,
            "motor": 1,
        })
        step = Z_STEP_UM + random.gauss(0.0, Z_STEP_SD_UM)
        if random.random() < SKIP_PROB:
            step *= 2
        if clean_force(z + step, p) > p["stop"]:
            break
        z += step
        i += 1

    # Final indent point at the force limit, after a larger Z step (as in the CSV)
    z_max = z + FINAL_STEP_UM + random.gauss(0.0, Z_STEP_SD_UM)
    f_peak = random.uniform(*FINAL_FORCE_RANGE_UN)
    out.append({
        "z_um": z_max,
        "force_uN": f_peak,
        "phase": 0,
        "motor": 1,
    })

    if INCLUDE_RETRACT:
        # Contact force at Z=0; residual depth where unload returns to baseline
        f0 = out[0]["force_uN"]
        z_res = RESIDUAL_DEPTH_FRACTION * z_max
        n_retract = len(out) - 1
        for k in range(1, n_retract + 1):
            zr = z_max * (1 - k / n_retract)
            if zr <= z_res:
                f = f0
            else:
                f = f0 + (f_peak - f0) * ((zr - z_res) / (z_max - z_res)) ** UNLOAD_EXPONENT
            # Retract sample: phase 1, motor still moving until flush below
            out.append({
                "z_um": zr,
                "force_uN": noisy(zr, f, k, p),
                "phase": 1,
                "motor": 1,
            })
    return out


# Device credentials embedded in every published telemetry payload
DEVICE_ID = "TsmfTUI5FCAf"
DEVICE_TOKEN = "q23GeDPV02xybXxT"


def build_payload(sample):
    """Build one MQTT JSON payload from a curve sample dict."""
    return {
        "displacement": DISPLACEMENT_SIGN * sample["z_um"] * UM_TO_M * OUTPUT_SCALE,  # mm
        "force": FORCE_SIGN * sample["force_uN"] * UN_TO_N * OUTPUT_SCALE,            # mN
        "phase": sample["phase"],
        # mqtt_client accepts "motor" and normalizes to motor_working
        "motor": sample["motor"],
        "timestamp": datetime.now().isoformat(),
        "device_id": DEVICE_ID,
        "device_token": DEVICE_TOKEN,
    }


# MQTT client
client = mqtt.Client(client_id="publisher_device_id", protocol=mqtt.MQTTv311, clean_session=False)
client.on_connect = on_connect
client.connect(broker, port, 60)
client.loop_start()

total_messages_sent = 0
interval = 1.0 / PUBLISH_RATE_HZ


def publish(sample):
    global total_messages_sent
    client.publish(topic, orjson.dumps(build_payload(sample)), qos=1, retain=False)
    total_messages_sent += 1


# Last sample published; used to force motor=0 if interrupted mid-curve
last_sample = None

try:
    for n in range(1, num_curves + 1):
        curve = curve_samples()
        next_t = time.time()
        for sample in curve:
            publish(sample)
            last_sample = sample
            next_t += interval
            time.sleep(max(0.0, next_t - time.time()))

        # Repeat last pose with motor idle so the backend flushes this curve
        flush = dict(last_sample)
        flush["motor"] = 0
        publish(flush)
        last_sample = flush
        print(f"Curve {n}/{num_curves} sent ({len(curve)} points)")

        if n < num_curves:
            time.sleep(CURVE_PAUSE_S)

    print(f"All {num_curves} curve(s) sent, {total_messages_sent} messages. Flushing in-flight publishes...")
    # Give a moment for any in-flight QoS1 messages to complete
    time.sleep(0.5)

except KeyboardInterrupt:
    print("Stopped by user")
    # Flush on Ctrl-C if a curve was in progress
    if last_sample is not None and last_sample["motor"] == 1:
        flush = dict(last_sample)
        flush["motor"] = 0
        publish(flush)
        print("Sent motor=0 flush after interrupt")

finally:
    client.loop_stop()
    client.disconnect()
    print("Program finished.")
    sys.exit(0)