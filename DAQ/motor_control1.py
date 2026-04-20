# motor_ctrl.py
# motor code wrapped for GUI control
# Supports explicit URI like: xi-com:///dev/ttyACM0

from ctypes import *
import time, os, sys, platform, tempfile, re
import numpy as np
import RPi.GPIO as GPIO
import threading, queue

if sys.version_info >= (3,0):
    import urllib.parse
from time import monotonic

# ---- Pins / motion constants (same as your script) ----
TRIP_IN = 22
SOFT_IN = 26
GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIP_IN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(SOFT_IN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

TRIP_LATCHED = False
SOFT_LATCHED = False
STEP_TO_MM = 0.000033333  # fallback/local A (mm per FULL step)
BASE_SPEED = 2000
BASE_ACCEL = 8000
BASE_DECEL = 8000
CREEP_SPEED = 200

# Log file written by MotorWorker (module-level so other scripts can import it)
MOTOR_FEED = "/tmp/motor_feed.txt"
__all__ = ["MotorWorker", "MOTOR_FEED"]

# ---- Locate pyximc (relative to this file, like your tree) ----
cur_dir = os.path.abspath(os.path.dirname(__file__))
ximc_dir = os.path.join(cur_dir, "..", "..", "..", "..", "ximc")
ximc_package_dir = os.path.join(ximc_dir, "crossplatform", "wrappers", "python")
sys.path.append(ximc_package_dir)

if platform.system() == "Windows":
    arch_dir = "win64" if "64" in platform.architecture()[0] else "win32"
    libdir = os.path.join(ximc_dir, arch_dir)
    if sys.version_info >= (3,8):
        os.add_dll_directory(libdir)
    else:
        os.environ["Path"] = libdir + ";" + os.environ["Path"]

# --- Ensure 'lib' is defined ---
_PYXIMC_OK = False
try:
    import pyximc as _px
    from pyximc import *          # types, structs, enums
    lib = _px.lib
    _PYXIMC_OK = True
except Exception as e:
    print("pyximc import warning:", e)
    lib = None

# =========================
# USER-UNITS (mm) HELPERS
# =========================
def _micro_divisor_from_engine(lib, device_id, default=256):
    """
    Returns (divisor, MicrostepMode_enum_value).
    divisor = 2^(MicrostepMode-1) as per XIMC docs.
    """
    try:
        eng = engine_settings_t()
        r = lib.get_engine_settings(device_id, byref(eng))
        if r == Result.Ok and eng.MicrostepMode:
            micro_mode = int(eng.MicrostepMode)
            div = 1 << max(0, micro_mode - 1)
            return float(div), micro_mode
    except Exception:
        pass
    return float(default), MicrostepMode.MICROSTEP_MODE_FRAC_256

def _make_local_cal(A_mm_per_step, micro_mode):
    cal = calibration_t()
    cal.A = float(A_mm_per_step)
    cal.MicrostepMode = int(micro_mode)
    return cal


def saw_trip():
    return GPIO.input(TRIP_IN) == GPIO.HIGH

def saw_soft():
    return GPIO.input(SOFT_IN) == GPIO.HIGH

def test_info(lib, device_id):
    x_device_information = device_information_t()
    result = lib.get_device_information(device_id, byref(x_device_information))
    if result == Result.Ok:
        print("Device:", repr(string_at(x_device_information.ProductDescription).decode()))

def test_status(lib, device_id):
    x_status = status_t()
    result = lib.get_status(device_id, byref(x_status))
    if result == Result.Ok:
        print("Flags:", hex(x_status.Flags))

def test_get_position(lib, device_id):
    x_pos = get_position_t()
    result = lib.get_position(device_id, byref(x_pos))
    return x_pos.Position, x_pos.uPosition

def test_movr(lib, device_id, distance, udistance):
    print("\nGoing to {0} steps, {1} microsteps".format(distance, udistance))
    result= lib.command_movr(device_id, distance, udistance)
    print("Result:", repr(result))

def retract(lib, device_id, distance, udistance):
    print("\nRetracting. Going to {0} steps, {1} microsteps".format(distance, udistance))
    lib.command_movr(device_id, distance, udistance)
    lib.command_wait_for_stop(device_id, 100)

def test_left(lib, device_id):
    print("\nMoving left")
    result = lib.command_left(device_id)
    print("Result:", repr(result))

def test_right(lib, device_id):
    print("\nMoving right")
    result = lib.command_right(device_id)
    print("Result:", repr(result))

def test_move(lib, device_id, distance, udistance):
    print("\nGoing to {0} steps, {1} microsteps".format(distance, udistance))
    result = lib.command_move(device_id, distance, udistance)
    print("Result:", repr(result))

def test_wait_for_stop(lib, device_id, interval):
    result = lib.command_wait_for_stop(device_id, interval)
    print("Wait stop result:", repr(result))

def test_serial(lib, device_id):
    x_serial = c_uint()
    result = lib.get_serial_number(device_id, byref(x_serial))
    if result == Result.Ok:
        print("Serial:", repr(x_serial.value))

def test_get_speed(lib, device_id):
    mvst = move_settings_t()
    result = lib.get_move_settings(device_id, byref(mvst))
    print("Read cmd:", repr(result))
    return mvst.Speed

def test_set_speed(lib, device_id, speed):
    mvst = move_settings_t()
    result = lib.get_move_settings(device_id, byref(mvst))
    print("Read cmd:", repr(result))
    print("Speed {0} -> {1}".format(mvst.Speed, speed))
    mvst.Speed = int(speed)
    result = lib.set_move_settings(device_id, byref(mvst))
    print("Write cmd:", repr(result))

def test_get_accel(lib, device_id):
    mvst = move_settings_t()
    result = lib.get_move_settings(device_id, byref(mvst))
    print("Accel:", mvst.Accel, "Decel:", mvst.Decel)

def test_set_microstep_mode_256(lib, device_id):
    eng = engine_settings_t()
    result = lib.get_engine_settings(device_id, byref(eng))
    eng.MicrostepMode = MicrostepMode.MICROSTEP_MODE_FRAC_256
    result = lib.set_engine_settings(device_id, byref(eng))
    print("Set microstep 256:", repr(result))

def read_calibration(lib, device_id):
    # Left intact, but NOT used in connect path to avoid segfault on some firmware.
    cal = calibration_t()
    r = lib.get_calibration_settings(device_id, byref(cal))
    if r == Result.Ok:
        print("\n--- USER UNIT CALIBRATION ---")
        print(f"A constant: {cal.A}")
        print(f"MicrostepMode: {cal.MicrostepMode}")
        print(f"Steps per user unit (1/A): {1.0 / cal.A if cal.A != 0 else '∞'}")
        print("-----------------------------")
    else:
        print("Failed to read calibration settings")

def apply_creep_speed(lib, device_id, creep_speed=CREEP_SPEED, keep_decel=BASE_DECEL):
    mv = move_settings_t()
    r1 = lib.get_move_settings(device_id, byref(mv))
    old_speed, old_decel = mv.Speed, mv.Decel
    mv.Speed = max(1, int(creep_speed))
    if keep_decel is not None:
        mv.Decel = int(keep_decel)
    r2 = lib.set_move_settings(device_id, byref(mv))
    print(f"creep get={r1} set={r2} : {old_speed}->{mv.Speed}, decel {old_decel}->{mv.Decel}")

def nudge_more_steps_same_direction(lib, device_id, steps=-200):
    x_pos = get_position_t()
    lib.get_position(device_id, byref(x_pos))
    target_steps = x_pos.Position + steps
    lib.command_move(device_id, target_steps, x_pos.uPosition)

def init_motion_profile(lib, device_id, speed, accel, decel):
    mv = move_settings_t()
    lib.get_move_settings(device_id, byref(mv))
    mv.Speed = int(speed)
    mv.Accel = int(accel)
    mv.Decel = int(decel)
    r = lib.set_move_settings(device_id, byref(mv))
    print(f"init_motion_profile -> {r}, Speed={mv.Speed}, Accel={mv.Accel}, Decel={mv.Decel}")

# --- Calibrated (mm) wrappers — LOCAL cal only ---
def set_move_settings_mm(lib, device_id, speed_mm_s, accel_mm_s2, decel_mm_s2, cal):
    mv = move_settings_calb_t()
    r1 = lib.get_move_settings_calb(device_id, byref(mv), byref(cal))
    mv.Speed  = float(speed_mm_s)
    mv.Accel  = float(accel_mm_s2)
    mv.Decel  = float(decel_mm_s2)
    r2 = lib.set_move_settings_calb(device_id, byref(mv), byref(cal))
    print(f"set_move_settings_calb: get={r1} set={r2} -> Speed={mv.Speed} mm/s, Accel={mv.Accel}, Decel={mv.Decel}")

def movr_mm(lib, device_id, delta_mm, cal):
    r = lib.command_movr_calb(device_id, c_float(delta_mm), byref(cal))
    print(f"command_movr_calb({delta_mm} mm) -> {r}")

# ---- Worker ----
class MotorWorker(threading.Thread):
    """
    Commands (tuples) via cmdq:
      ("connect", uri_or_None)
      ("jog", steps:int)               # step move
      ("cont_move", "down"/"up")       # continuous move; stop with ("stop", None)
      ("speed", speed:int)

      # NEW user-unit commands
      ("speed_mm", mm_per_s:float)     # set speed in mm/s (uses local cal)
      ("jog_mm", delta_mm:float)       # relative mm move (uses local cal)

      ("stop", None)                   # stop motion
      ("estop", None)                  # soft stop immediately
      ("quit", None)
    """
    def __init__(self, cmdq: "queue.Queue", uiq: "queue.Queue", default_uri: str = None):
        super().__init__(daemon=True)
        self.cmdq = cmdq
        self.uiq = uiq
        self.stop_flag = False
        self.lib = None
        self.device_id = None
        self.connected = False
        self.spos = 0
        self.supos = 0
        self.default_uri = default_uri

        # Local/user-unit cache
        self.A_mm_per_step = STEP_TO_MM
        self.micro_div = 256.0
        self.micro_mode = MicrostepMode.MICROSTEP_MODE_FRAC_256
        self.cal = _make_local_cal(self.A_mm_per_step, self.micro_mode)

        # Defaults for mm mode
        self.mm_accel = 2.0
        self.mm_decel = 2.0

    def _connect(self, uri: str = None):
        try:
            if uri is None:
                uri = self.default_uri

            if uri:
                open_name = uri.encode() if isinstance(uri, str) else uri
                self.device_id = lib.open_device(open_name)
                self.lib = lib
            else:
                probe_flags = (EnumerateFlags.ENUMERATE_USB |
                               EnumerateFlags.ENUMERATE_PROBE |
                               EnumerateFlags.ENUMERATE_NETWORK)
                enum_hints = b"addr="
                devenum = lib.enumerate_devices(probe_flags, enum_hints)
                dev_count = lib.get_device_count(devenum)
                if dev_count <= 0:
                    self.uiq.put("Motor: no controller found.")
                    return False
                open_name = lib.get_device_name(devenum, 0)
                if type(open_name) is str:
                    open_name = open_name.encode()
                self.device_id = lib.open_device(open_name)
                self.lib = lib

            # Init path (same as your script)
            test_info(lib, self.device_id)
            test_status(lib, self.device_id)
            test_set_microstep_mode_256(lib, self.device_id)
            init_motion_profile(lib, self.device_id, BASE_SPEED, BASE_ACCEL, BASE_DECEL)
            test_get_speed(lib, self.device_id)
            test_get_accel(lib, self.device_id)

            x_pos = get_position_t()
            _ = lib.get_position(self.device_id, byref(x_pos))
            self.spos, self.supos = x_pos.Position, x_pos.uPosition

            # === SAFE: read only engine microstep, build local calibration ===
            self.micro_div, self.micro_mode = _micro_divisor_from_engine(self.lib, self.device_id, default=256)
            self.A_mm_per_step = float(STEP_TO_MM)  # your known scale
            self.cal = _make_local_cal(self.A_mm_per_step, self.micro_mode)
            self.uiq.put(f"Motor cal (local): A={self.A_mm_per_step:.9g} mm/step, "
                         f"MicrostepMode={int(self.micro_mode)}, divisor={int(self.micro_div)}")

            self.connected = True
            self.uiq.put("Motor: connected.")
            return True
        except Exception as e:
            self.uiq.put(f"Motor: connect failed: {e}")
            return False

    def _close(self):
        try:
            test_wait_for_stop(self.lib, self.device_id, 100)
            self.uiq.put("Motor: closing.")
            lib.close_device(byref(cast(self.device_id, POINTER(c_int))))
        except Exception:
            pass

    def run(self):
        self.uiq.put("Motor: ready.")
        try:
            with open('new.txt','w') as f, open(MOTOR_FEED,'w', buffering=1) as motor_feed:
                inittime = time.monotonic_ns()
                zpre = 0
                tpre = 0
                t_trip_ms = None
                global TRIP_LATCHED, SOFT_LATCHED

                while not self.stop_flag:
                    # Commands
                    try:
                        while True:
                            cmd, arg = self.cmdq.get_nowait()
                            if cmd == "connect":
                                if not self.connected:
                                    self._connect(arg if isinstance(arg, str) and arg.strip() else None)
                                else:
                                    self.uiq.put("Motor: already connected.")

                            elif cmd == "jog" and self.connected:
                                steps = int(arg)
                                x_pos = get_position_t()
                                self.lib.get_position(self.device_id, byref(x_pos))
                                target = x_pos.Position + steps
                                r = self.lib.command_move(self.device_id, target, x_pos.uPosition)
                                self.uiq.put(f"Motor: jog {steps} -> r={r}")

                            elif cmd == "cont_move" and self.connected:
                                direction = str(arg).lower()
                                if direction == "down":
                                    test_left(self.lib, self.device_id)
                                    self.uiq.put("Motor: continuous DOWN (hold).")
                                elif direction == "up":
                                    test_right(self.lib, self.device_id)
                                    self.uiq.put("Motor: continuous UP (hold).")

                            elif cmd == "speed" and self.connected:
                                test_set_speed(self.lib, self.device_id, int(arg))
                                self.uiq.put(f"Motor: speed set {int(arg)} steps/s")

                            # ---- NEW user-units (mm) commands ----
                            elif cmd == "speed_mm" and self.connected:
                                speed_mm = float(arg)
                                set_move_settings_mm(self.lib, self.device_id,
                                                     speed_mm_s=speed_mm,
                                                     accel_mm_s2=self.mm_accel,
                                                     decel_mm_s2=self.mm_decel,
                                                     cal=self.cal)
                                self.uiq.put(f"Motor: speed set {speed_mm} mm/s")

                            elif cmd == "jog_mm" and self.connected:
                                delta_mm = float(arg)
                                movr_mm(self.lib, self.device_id, delta_mm, self.cal)
                                self.uiq.put(f"Motor: jog_mm {delta_mm} mm")

                            elif cmd == "stop" and self.connected:
                                try: self.lib.command_stop(self.device_id)
                                except: pass
                                self.uiq.put("Motor: stop.")

                            elif cmd == "estop" and self.connected:
                                try: self.lib.command_sstp(self.device_id)
                                except: pass
                                self.uiq.put("Motor: E-STOP.")

                            elif cmd == "quit":
                                self.stop_flag = True
                                break
                    except queue.Empty:
                        pass
                    if self.stop_flag:
                        break

                    if not self.connected:
                        time.sleep(0.05)
                        continue

                    # SOFT guard
                    if saw_soft() and not SOFT_LATCHED:
                        SOFT_LATCHED = True
                        self.uiq.put(">>> SOFT guard: reduce speed to creep")
                        apply_creep_speed(self.lib, self.device_id, creep_speed=CREEP_SPEED)

                    # Read position and log (uses local A and divisor)
                    x_pos = get_position_t()
                    result = self.lib.get_position(self.device_id, byref(x_pos))
                    pos, upos = x_pos.Position, x_pos.uPosition
                    Z = (pos - self.spos) + ((upos - self.supos)/float(self.micro_div))

                    T = time.monotonic_ns() - inittime
                    dZ = Z - zpre
                    dT = (T - tpre)/1.0e6
                    timee = T/1.0e6
                    t_pi_abs = time.monotonic()

                    disp_mm = self.A_mm_per_step * Z
                    motor_feed.write(f"{t_pi_abs:.9f} {disp_mm}\n")

                    # HARD trip
                    if saw_trip() and not TRIP_LATCHED:
                        TRIP_LATCHED = True
                        t_trip_ms = timee
                        self.uiq.put(">>> HARD TRIP detected: stopping + retract")
                        try:
                            self.lib.command_stop(self.device_id)
                        except:
                            pass
                        time.sleep(0.01)

                    f.write(f"{Z} {timee} {pos} {upos} {dZ} {dT} {0.0} {self.spos} {self.supos}\n")
                    zpre = Z
                    tpre = T

                    time.sleep(0.001)
        finally:
            try:
                if self.connected:
                    self._close()
            except:
                pass
            self.uiq.put("Motor: thread exit.")

# Standalone quick test
if __name__ == "__main__":
    cq, uq = queue.Queue(), queue.Queue()
    w = MotorWorker(cq, uq, default_uri="xi-com:///dev/ttyACM0"); w.start()
    cq.put(("connect", "xi-com:///dev/ttyACM0"))
    try:
        while True:
            try:
                print(uq.get(timeout=0.2))
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        cq.put(("quit", None))
