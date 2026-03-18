#!/usr/bin/env python3
import os, sys, time, json, threading, queue
from datetime import datetime, timezone

# ---------------- ENV ----------------
BROKER_HOST  = os.getenv("MQTT_HOST", "localhost")
BROKER_PORT  = int(os.getenv("MQTT_PORT", "1883"))
TOPIC        = os.getenv("MQTT_TOPIC", "MON")

MOTOR_FILE   = os.getenv("MOTOR_FEED", "/tmp/motor_feed.txt")   # "<ts> <disp>"
FORCE_FILE   = os.getenv("FORCE_FEED", "/tmp/force_feed.txt")   # "<ts> <counts> [volts] [mN]"

DEVICE_ID    = os.getenv("DEVICE_ID", "HqSTf2PYpg6t")
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", "av40HTAb0O5VGQ0D")

PUBLISH_HZ   = float(os.getenv("PUBLISH_HZ", "100"))

# What to publish for "force": "mn" | "volts" | "counts"
FORCE_UNIT   = os.getenv("FORCE_PUBLISH_UNIT", "mn").strip().lower()

# If converting:
#   mN = CAL_MN_PER_V * volts + CAL_OFFSET_MN
CAL_MN_PER_V   = float(os.getenv("CAL_MN_PER_V",   "1.0"))   # slope (mN per Volt)
CAL_OFFSET_MN  = float(os.getenv("CAL_OFFSET_MN",  "0.0"))   # offset (mN)
# If only counts are available and you want volts:
#   volts = (counts - ADC_ZERO) * ADC_V_PER_COUNT
ADC_V_PER_COUNT = float(os.getenv("ADC_V_PER_COUNT", "0.0"))  # e.g. 0.000125 V/count
ADC_ZERO        = float(os.getenv("ADC_ZERO",        "0.0"))  # counts at 0 V
# -------------------------------------

# ---- Paho client (v1 & v2 compatible) ----
try:
    import paho.mqtt.client as mqtt
    try:
        client = mqtt.Client(
            client_id="publisher_device_id",
            protocol=mqtt.MQTTv311,
            clean_session=True,
            userdata=None,
            callback_api_version=getattr(mqtt, "CallbackAPIVersion", None).V1
        )
    except Exception:
        client = mqtt.Client(client_id="publisher_device_id", protocol=mqtt.MQTTv311, clean_session=True)
except Exception as e:
    print(f"[FATAL] paho-mqtt not available: {e}", flush=True)
    sys.exit(2)
# -------------------------------------------

def parse_force_row(parts):
    """
    parts: list of strings from one FORCE file line.
    Expected: ts counts [volts] [mN]
    Returns tuple: (ts, value_for_publishing, dbg_counts, dbg_volts, dbg_mn)
    """
    ts = float(parts[0])
    counts = float(parts[1]) if len(parts) >= 2 else None
    volts  = float(parts[2]) if len(parts) >= 3 else None
    mN_col = float(parts[3]) if len(parts) >= 4 else None

    # Decide what to publish
    if FORCE_UNIT == "mn":
        if mN_col is not None:
            force_val = mN_col
        elif volts is not None:
            force_val = CAL_MN_PER_V * volts + CAL_OFFSET_MN
        elif (counts is not None) and (ADC_V_PER_COUNT > 0.0):
            v = (counts - ADC_ZERO) * ADC_V_PER_COUNT
            force_val = CAL_MN_PER_V * v + CAL_OFFSET_MN
        else:
            # fallback: raw counts if we can't convert
            force_val = counts
    elif FORCE_UNIT == "volts":
        if volts is not None:
            force_val = volts
        elif (counts is not None) and (ADC_V_PER_COUNT > 0.0):
            force_val = (counts - ADC_ZERO) * ADC_V_PER_COUNT
        else:
            force_val = counts
    else:  # "counts"
        force_val = counts

    return ts, force_val, counts, volts, mN_col

def follow_file(path, out_q, kind):
    """Tail a whitespace file and push tuples to queue."""
    last_log = 0.0
    while not os.path.exists(path):
        now = time.time()
        if now - last_log > 1.0:
            print(f"[{kind}] waiting for {path} ...", flush=True)
            last_log = now
        time.sleep(0.05)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        f.seek(0, os.SEEK_END)  # start at end (stream only new lines)
        buf = ""
        while True:
            chunk = f.read()
            if not chunk:
                time.sleep(0.003)
                continue
            buf += chunk
            while True:
                j = buf.find("\n")
                if j < 0:
                    break
                line = buf[:j].strip()
                buf  = buf[j+1:]
                if not line:
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                try:
                    if kind == "force":
                        ts, val, c_dbg, v_dbg, mn_dbg = parse_force_row(parts)
                        out_q.put(("force", ts, val, c_dbg, v_dbg, mn_dbg), block=False)
                    else:
                        # MOTOR: "<ts> <disp>" (pass through)
                        ts = float(parts[0]); val = float(parts[1])
                        out_q.put(("disp", ts, val), block=False)
                except Exception:
                    pass  # ignore malformed rows

def main():
    def on_connect(client, userdata, flags, rc, properties=None):
        print(f"[MQTT] connected rc={rc} host={BROKER_HOST} port={BROKER_PORT} topic={TOPIC}", flush=True)
    client.on_connect = on_connect

    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    except Exception as e:
        print(f"[FATAL] MQTT connect failed: {e}", flush=True)
        sys.exit(2)

    client.loop_start()

    q = queue.Queue(maxsize=50000)
    threading.Thread(target=follow_file, args=(MOTOR_FILE, q, "disp"),  daemon=True).start()
    threading.Thread(target=follow_file, args=(FORCE_FILE, q, "force"), daemon=True).start()

    latest_disp  = None                  # (ts, value)
    latest_force = None                  # (ts, value, counts_dbg, volts_dbg, mn_dbg)
    min_period = 1.0 / max(1.0, PUBLISH_HZ)
    last_pub   = 0.0
    sent = 0
    t0 = time.time()

    print(f"[RUN] Publishing displacement + force ({FORCE_UNIT}) at ≤{PUBLISH_HZ:g} Hz → {TOPIC}", flush=True)

    while True:
        # Drain bursts
        for _ in range(400):
            try:
                item = q.get_nowait()
            except queue.Empty:
                break

            if item[0] == "disp":
                _, ts, val = item
                latest_disp = (ts, val)
            else:
                _, ts, val, c_dbg, v_dbg, mn_dbg = item
                latest_force = (ts, val, c_dbg, v_dbg, mn_dbg)

        now = time.time()
        if (latest_disp is not None) and (latest_force is not None) and (now - last_pub) >= min_period:
            payload = {
                "timestamp":    datetime.now(timezone.utc).isoformat(),
                "displacement": latest_disp[1],      # unchanged (your units)
                "force":        latest_force[1],     # per FORCE_UNIT
                "device_id":    DEVICE_ID,
                "device_token": DEVICE_TOKEN,
                # Debug (remove if you truly want only two fields at the backend):
                "t_disp":       latest_disp[0],
                "t_force":      latest_force[0],
            }
            client.publish(TOPIC, json.dumps(payload), qos=1)
            last_pub = now
            sent += 1
            if sent % 200 == 0:
                rate = sent / (now - t0)
                print(
                    f"[PUB] {sent} ~{rate:.1f} Hz  disp={payload['displacement']:.6g}  "
                    f"force({FORCE_UNIT})={payload['force']:.6g}",
                    flush=True
                )

        time.sleep(0.002)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
