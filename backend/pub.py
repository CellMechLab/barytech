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
if len(sys.argv) != 3:
    print("Usage: python publisher.py <points_per_batch> <total_points>")
    sys.exit(1)

try:
    points_per_batch = int(sys.argv[1])
    total_points = int(sys.argv[2])
except ValueError:
    print("Error: arguments must be integers.")
    sys.exit(1)

if points_per_batch <= 0 or total_points <= 0:
    print("Error: arguments must be positive integers.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Curve model — shape taken from processed_data_0.2kPa 1.csv (10 curves),
# rescaled to Z 0 -> ~30 um and force ~50 uN -> ~350 uN (force limit).
#   In the CSV, force rises slowly then steeply (convex, ~power law), then
#   flattens just before the limit; ~122 points per curve.
#   Noise: even/odd zigzag + random scatter, both growing with force.
# Internally um / uN; published in SI (m / N), both positive.
# ---------------------------------------------------------------------------
DISPLACEMENT_SIGN = 1           # positive displacement (set -1 if the backend expects negative)
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
    motor: 1 for every live sample. A single motor=0 is published after the
    whole CLI run finishes so the dashboard can close the folder save curve.
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


def sample_stream():
    """Endless stream of live samples with motor=1 (indent still running).

    motor=0 is NOT emitted between curves. The publisher sends a single
    motor=0 after all CLI points are done so the frontend/backend can close
    the save session and treat the run as one finished curve.
    """
    while True:
        yield from curve_samples()


# Device credentials embedded in every published telemetry payload
DEVICE_ID = "TsmfTUI5FCAf"
DEVICE_TOKEN = "q23GeDPV02xybXxT"


def build_payload(sample):
    """Build one MQTT JSON payload from a curve sample dict."""
    # Motor activity flag mirrored as state for older clients that only watch state
    motor = sample["motor"]
    return {
        "displacement": DISPLACEMENT_SIGN * sample["z_um"] * UM_TO_M,  # m
        "force": sample["force_uN"] * UN_TO_N,                         # N
        "phase": sample["phase"],
        # mqtt_client accepts "motor" and normalizes to motor_working
        "motor": motor,
        # 1 = indent in progress, 0 = finished — closes folder save on the dashboard
        "state": motor,
        "timestamp": datetime.now().isoformat(),
        "device_id": DEVICE_ID,
        "device_token": DEVICE_TOKEN,
    }


def publish_motor_stop(sample):
    """Publish motor=0 / state=0 so the backend folder save closes this curve."""
    flush = dict(sample)
    flush["motor"] = 0
    client.publish(topic, orjson.dumps(build_payload(flush)), qos=1, retain=False)
    print("Sent motor=0 — indentation stopped, curve ready to save")


# MQTT client
client = mqtt.Client(client_id="publisher_device_id", protocol=mqtt.MQTTv311, clean_session=False)
client.on_connect = on_connect
client.connect(broker, port, 60)
client.loop_start()

# Running count of published MQTT messages (live points only; stop is extra)
total_messages_sent = 0
# Last live sample; reused for the final motor=0 stop message
last_sample = None
samples = sample_stream()

try:
    # Loop only while we still have points to send
    while total_messages_sent < total_points:
        start_time = time.time()
        messages_sent = 0

        for _ in range(points_per_batch):
            if total_messages_sent >= total_points:
                break

            sample = next(samples)
            payload = build_payload(sample)

            # Use retain=False for streaming telemetry
            info = client.publish(topic, orjson.dumps(payload), qos=1, retain=False)
            # Optional: wait for QoS1 ack for each message (can be skipped for speed)
            # info.wait_for_publish()

            last_sample = sample
            messages_sent += 1
            total_messages_sent += 1

        elapsed = time.time() - start_time
        time.sleep(max(0, 1 - elapsed))
        print(f"Sent {messages_sent} msgs this round, Total: {total_messages_sent}")

    # After ALL points: motor=0 tells the dashboard indentation finished and
    # the open folder save session should close this curve.
    if last_sample is not None:
        publish_motor_stop(last_sample)

    print("All messages sent. Flushing in-flight publishes...")

    # Give a moment for any in-flight QoS1 messages to complete
    time.sleep(0.5)

except KeyboardInterrupt:
    print("Stopped by user")
    # Same stop signal on Ctrl-C so a partial run still closes the curve
    if last_sample is not None:
        publish_motor_stop(last_sample)

finally:
    client.loop_stop()
    client.disconnect()
    print("Program finished.")
    sys.exit(0)