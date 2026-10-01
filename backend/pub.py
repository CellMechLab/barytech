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
# Curve model — fitted to processed_data_0.2kPa_S1_1.csv (10 curves):
#   Z indent 0 -> ~32 um in ~0.55 um steps (57-60 points per curve),
#   force ~142 uN at contact -> ~350 uN, where the indent stops (force limit).
#   Noise: even/odd zigzag + random scatter, both growing with depth.
# Internally um / uN; published in SI (m / N).
# ---------------------------------------------------------------------------
DISPLACEMENT_SIGN = -1          # set 1 if the backend expects positive displacement
INCLUDE_RETRACT = True          # False -> only indent legs (what the CSV contains)

# Mean force (uN) of the 10 reference curves at Z = 0, 1, 2 ... 31 um
# (the last two show the flattening just before the force limit).
TEMPLATE_UN = [
    142.1, 144.6, 148.2, 152.2, 156.4, 159.9, 164.0, 167.9, 172.7, 177.5,
    182.3, 186.5, 191.4, 197.1, 202.9, 208.8, 215.0, 220.9, 227.8, 235.1,
    242.3, 249.7, 257.5, 265.9, 275.2, 284.7, 294.6, 305.1, 315.1, 326.6,
    335.3, 340.4,
]
TEMPLATE_STEP_UM = 1.0
TAIL_SLOPE_UN_PER_UM = 5.0      # extrapolation beyond the template

Z_STEP_UM = 0.5504              # sampling step in Z
Z_STEP_SD_UM = 0.015
SKIP_PROB = 0.03                # occasional skipped sample (double step)

F0_SD_UN = 1.0                  # contact force spread between curves
SCALE_SD = 0.012                # stiffness spread between curves

FORCE_STOP_UN = 341.0           # indent stops when the next point would exceed this ...
FORCE_STOP_SD_UN = 1.5
FINAL_FORCE_RANGE_UN = (341.0, 350.0)  # ... and a final point lands here, ~1.1 um further
FINAL_STEP_UM = 1.1

ZIGZAG_UN = (0.8, 0.05)         # alternating noise amplitude = a + b*z
SCATTER_UN = (1.0, 0.08)        # gaussian noise SD = a + b*z

RESIDUAL_DEPTH_FRACTION = 0.15  # retract: force back at baseline at this depth fraction
UNLOAD_EXPONENT = 1.8

UM_TO_M = 1e-6
UN_TO_N = 1e-6


def template_force(z):
    """Mean reference force (uN) at Z (um), linear interpolation."""
    if z <= 0:
        return TEMPLATE_UN[0]
    pos = z / TEMPLATE_STEP_UM
    i = int(pos)
    if i >= len(TEMPLATE_UN) - 1:
        return TEMPLATE_UN[-1] + TAIL_SLOPE_UN_PER_UM * (z - (len(TEMPLATE_UN) - 1) * TEMPLATE_STEP_UM)
    t = pos - i
    return TEMPLATE_UN[i] * (1 - t) + TEMPLATE_UN[i + 1] * t


def make_curve_params():
    return {
        "f0_offset": random.gauss(0.0, F0_SD_UN),
        "scale": random.gauss(1.0, SCALE_SD),
        "stop": random.gauss(FORCE_STOP_UN, FORCE_STOP_SD_UN),
        "zig_phase": random.choice((-1, 1)),
    }


def clean_force(z, p):
    base = TEMPLATE_UN[0]
    return base + p["f0_offset"] + (template_force(z) - base) * p["scale"]


def noisy(z, f, i, p):
    zig = (ZIGZAG_UN[0] + ZIGZAG_UN[1] * z) * p["zig_phase"] * (-1) ** i
    return f + zig + random.gauss(0.0, SCATTER_UN[0] + SCATTER_UN[1] * z)


def curve_samples():
    """One full curve as a list of (z_um, force_uN)."""
    p = make_curve_params()
    out = []
    z, i = 0.0, 0
    while True:
        out.append((z, noisy(z, clean_force(z, p), i, p)))
        step = Z_STEP_UM + random.gauss(0.0, Z_STEP_SD_UM)
        if random.random() < SKIP_PROB:
            step *= 2
        if clean_force(z + step, p) > p["stop"]:
            break
        z += step
        i += 1

    # Final point at the force limit, after a larger Z step (as in the CSV)
    z_max = z + FINAL_STEP_UM + random.gauss(0.0, Z_STEP_SD_UM)
    f_peak = random.uniform(*FINAL_FORCE_RANGE_UN)
    out.append((z_max, f_peak))

    if INCLUDE_RETRACT:
        f0 = out[0][1]
        z_res = RESIDUAL_DEPTH_FRACTION * z_max
        n_retract = len(out) - 1
        for k in range(1, n_retract + 1):
            zr = z_max * (1 - k / n_retract)
            if zr <= z_res:
                f = f0
            else:
                f = f0 + (f_peak - f0) * ((zr - z_res) / (z_max - z_res)) ** UNLOAD_EXPONENT
            out.append((zr, noisy(zr, f, k, p)))
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

            z_um, force_uN = next(samples)
            timestamp = datetime.now().isoformat()

            payload = {
                "displacement": DISPLACEMENT_SIGN * z_um * UM_TO_M,  # m
                "force": force_uN * UN_TO_N,                         # N
                "timestamp": timestamp,
                "device_id": "TsmfTUI5FCAf",
                "device_token": "q23GeDPV02xybXxT",
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