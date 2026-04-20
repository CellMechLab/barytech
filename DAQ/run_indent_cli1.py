#!/usr/bin/env python3
# run_indent_cli.py — surface-detect → retract → slow-indent → save CSV + plot

import argparse, os, time, sys, csv, datetime, queue
import numpy as np
import matplotlib.pyplot as plt

from force_acq import ForceWorker, FORCE_FEED
from motor_control1 import MotorWorker, MOTOR_FEED

# ---------- I/O helpers ----------
def save_run_csv(disp_um, force, y_label, outdir="runs"):
    os.makedirs(outdir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(outdir, f"fvdisp_{stamp}.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["displacement_um", "force_value", "force_units"])
        for x, y in zip(disp_um, force):
            w.writerow([f"{float(x):.6f}", f"{float(y):.6f}", y_label])
    return path

def _safe_load_feed(path, synth_dt=0.001):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    try:
        arr = np.genfromtxt(path, comments="#", invalid_raise=False)
    except Exception:
        return None
    if arr is None:
        return None
    arr = np.atleast_2d(arr)
    if arr.size == 0:
        return None
    if arr.shape[1] == 1:
        y = arr[:, 0].astype(float)
        t = np.arange(y.shape[0], dtype=float) * float(synth_dt)
        arr = np.column_stack([t, y])
    if arr.shape[1] < 2:
        return None
    m = np.isfinite(arr[:, 0]) & np.isfinite(arr[:, 1])
    return arr[m] if np.any(m) else None

def build_force_disp_chrono(force_path=FORCE_FEED, motor_path=MOTOR_FEED, stop_at_max=True):
    F = _safe_load_feed(force_path)
    M = _safe_load_feed(motor_path)
    if F is None or M is None:
        return None

    tF = F[:, 0].astype(float)
    # prefer mN if available (col 4 in your logger), else raw counts
    if F.shape[1] >= 4:
        y = F[:, 3].astype(float); y_label = "Force (mN)"
    else:
        y = F[:, 1].astype(float);  y_label = "Force (ADC counts)"

    tM = M[:, 0].astype(float)
    dM_mm = M[:, 1].astype(float)

    if tF.size < 1 or tM.size < 2:
        return None

    t_lo = max(tF.min(), tM.min())
    t_hi = min(tF.max(), tM.max())
    if not (t_hi > t_lo):
        return None

    mF = (tF >= t_lo) & (tF <= t_hi)
    mM = (tM >= t_lo) & (tM <= t_hi)
    if not (np.any(mF) and np.any(mM)):
        return None

    tF_ov = tF[mF]
    y_ov  = y[mF]
    tM_ov = tM[mM]
    dM_ov = dM_mm[mM]

    # displacement at exact force timestamps (keep chronological)
    disp_um = np.interp(tF_ov, tM_ov, dM_ov).astype(float) * 1e3  # mm → µm
    if disp_um.size:
        disp_um = disp_um - disp_um[0]

    if stop_at_max and y_ov.size > 0:
        imax = int(np.argmax(y_ov))
        y_ov = y_ov[:imax+1]
        disp_um = disp_um[:imax+1]

    return disp_um, y_ov, y_label

def wait_for_file_growth(path, min_bytes=8, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(path) and os.path.getsize(path) >= min_bytes:
            return True
        time.sleep(0.05)
    return False

def latest_force_mN(force_path):
    """Return last force value in mN if available, else None (or counts if mN not present)."""
    F = _safe_load_feed(force_path)
    if F is None or F.size == 0:
        return None, None
    if F.shape[1] >= 4:
        return float(F[-1, 3]), "mN"
    else:
        return float(F[-1, 1]), "counts"

# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser(
        description="Indent with surface detection: fast approach → detect → retract → slow indent → CSV + plot"
    )
    ap.add_argument("--uri", default="xi-com:///dev/ttyACM0", help="XIMC URI (e.g., xi-com:///dev/ttyACM0)")

    # Fast approach phase
    ap.add_argument("--speed_fast_mm_s", type=float, default=0.10, help="fast approach speed (mm/s)")
    ap.add_argument("--approach_budget_mm", type=float, default=1.0, help="max distance to attempt during fast approach")

    # Surface detection
    ap.add_argument("--detect_threshold_mN", type=float, default=0.10, help="surface detect threshold (mN)")
    ap.add_argument("--detect_timeout_s", type=float, default=10.0, help="timeout for detection")

    # Back off and slow indent
    ap.add_argument("--retract_after_detect_um", type=float, default=20.0, help="retract after detection (µm)")
    ap.add_argument("--speed_slow_mm_s", type=float, default=0.010, help="slow indent speed (mm/s)")
    ap.add_argument("--indent_slow_mm", type=float, default=0.30, help="slow indent distance after retract (mm)")
    ap.add_argument("--max_force_mN", type=float, default=0.50, help="stop slow indent if this force reached (mN)")

    # Optional accel/decel that  MotorWorker may honor in mm-calb mode
    ap.add_argument("--accel_mm_s2", type=float, default=2.0, help="accel (mm/s^2)")
    ap.add_argument("--decel_mm_s2", type=float, default=2.0, help="decel (mm/s^2)")

    args = ap.parse_args()

    uiq = queue.Queue()
    force_cmdq = queue.Queue()
    motor_cmdq = queue.Queue()

    # Start workers
    force = ForceWorker(force_cmdq, uiq); force.start()
    motor = MotorWorker(motor_cmdq, uiq, default_uri=args.uri); motor.start()

    # Drain initial UI lines
    time.sleep(0.4)
    try:
        while True: print(uiq.get_nowait())
    except Exception:
        pass

    # Connect + configure motor
    motor_cmdq.put(("connect", args.uri))
    time.sleep(0.6)

    # Set fast speed (mm/s).
    motor_cmdq.put(("speed_mm", float(args.speed_fast_mm_s)))
    time.sleep(0.1)

    # Start force logging and make sure feeds exist
    force_cmdq.put("start")
    wait_for_file_growth(FORCE_FEED, timeout=3.0)
    wait_for_file_growth(MOTOR_FEED, timeout=3.0)

    # ---------------------
    # Phase 1: FAST APPROACH until surface detected
    # ---------------------
    motor_cmdq.put(("jog_mm", +abs(args.approach_budget_mm)))  

    t0 = time.time()
    detected = False
    while time.time() - t0 < args.detect_timeout_s:
        f_val, units = latest_force_mN(FORCE_FEED)
        if f_val is None:
            time.sleep(0.01)
            continue
        # If units are counts, we can't compare meaningfully—just keep approaching.
        if units == "mN" and f_val >= args.detect_threshold_mN:
            detected = True
            # Stop immediately
            motor_cmdq.put(("stop", None))
            break
        time.sleep(0.01)

    if not detected:
        # Could not detect surface within budget/time; stop and proceed to plot whatever was recorded.
        motor_cmdq.put(("stop", None))
        time.sleep(0.3)
        print("WARN: Surface not detected within threshold/time. Proceeding with whatever data is available.", file=sys.stderr)

    # ---------------------
    # Phase 2: RETRACT a hair + slow indent
    # ---------------------
    # ---------------------
    # Phase 2: RETRACT a hair + slow indent
    # ---------------------
    if detected:
        # retract a little to unload
        back_um = max(1.0, float(args.retract_after_detect_um))
        motor_cmdq.put(("jog_mm", -(back_um / 1e3)))  # µm → mm
        time.sleep(0.25)

        # slow speed for dense sampling
        motor_cmdq.put(("speed_mm", float(args.speed_slow_mm_s)))
        time.sleep(0.1)

        # do a slow indent, but stop early if we reach max force OR we run out of time
        motor_cmdq.put(("jog_mm", +abs(args.indent_slow_mm)))

        # ---- NEW: robust stop conditions for slow phase ----
        slow_t0 = time.time()
        # theoretical duration (distance / speed) plus a small buffer
        # protect against divide-by-zero if someone sets speed to 0
        if args.speed_slow_mm_s > 0:
            slow_t_max = (abs(args.indent_slow_mm) / args.speed_slow_mm_s) + 0.6
        else:
            slow_t_max = 5.0  # fall-back

        reached_force = False
        while True:
            f_val, units = latest_force_mN(FORCE_FEED)
            if f_val is not None and units == "mN" and f_val >= args.max_force_mN:
                reached_force = True
                motor_cmdq.put(("stop", None))
                break

            # timeout / distance-based exit so we don't hang forever
            if (time.time() - slow_t0) >= slow_t_max:
                motor_cmdq.put(("stop", None))
                break

            time.sleep(0.01)

        # ---- NEW: retract back roughly to pre-detect position ----
        # estimate how far we actually moved during slow phase
        elapsed = time.time() - slow_t0
        moved_mm = min(abs(args.indent_slow_mm), elapsed * max(args.speed_slow_mm_s, 0.0))
        # retract slow-indent distance + the small pre-indent back-off
        motor_cmdq.put(("jog_mm", -(moved_mm + back_um / 1e3)))
        time.sleep(0.3)


    # Build curve, save CSV, plot
    res = build_force_disp_chrono()
    if not res:
        print("ERROR: could not build force vs displacement (no overlap or empty feeds).", file=sys.stderr)
    else:
        x_um, y, y_label = res
        csv_path = save_run_csv(x_um, y, y_label)
        print(f"Saved run to: {csv_path}")

        plt.figure("Force vs Displacement")
        plt.plot(x_um, y, linewidth=1.2)
        plt.xlabel("Displacement (µm)")
        plt.ylabel(y_label)
        plt.title("Force vs Displacement (surface-detect → slow indent)")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()

    # Shutdown
    try: force_cmdq.put("quit")
    except: pass
    try: motor_cmdq.put(("quit", None))
    except: pass

    time.sleep(0.3)
    try:
        while True: print(uiq.get_nowait())
    except Exception:
        pass

if __name__ == "__main__":
    main()
