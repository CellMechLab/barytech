import serial
import time
import re
import sys

# --- Config ---
SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE   = 230400
TIMEOUT     = 5

# Movement step sizes (mm) — change these to your liking
STEP_SMALL  = 0.1
STEP_MEDIUM = 1.0
STEP_LARGE  = 10.0

CURRENT_STEP = STEP_MEDIUM          # default step size


def send(ser, cmd: str, wait_ok=True, timeout=5):
    """Send a G-code command and optionally wait for 'ok'."""
    full = (cmd.strip() + "\n").encode()
    ser.write(full)
    print(f"  → {cmd.strip()}")

    if not wait_ok:
        return

    deadline = time.time() + timeout
    while time.time() < deadline:
        line = ser.readline().decode(errors="ignore").strip()
        if line:
            print(f"  ← {line}")
        if line.startswith("ok"):
            return
    print("  ⚠ No 'ok' received — continuing anyway")


def get_position(ser):
    """Send M114 and return a dict {X, Y, Z, E}."""
    ser.reset_input_buffer()
    ser.write(b"M114\n")
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        line = ser.readline().decode(errors="ignore").strip()
        pos = {}
        for axis in ("X", "Y", "Z", "E"):
            m = re.search(rf"{axis}:(-?\d+\.\d+)", line)
            if m:
                pos[axis] = float(m.group(1))
        if pos:
            return pos
    return {}


def set_relative(ser):
    send(ser, "G91", wait_ok=True)   # relative positioning


def set_absolute(ser):
    send(ser, "G90", wait_ok=True)   # absolute positioning


def move(ser, axis: str, distance: float, feed: int = 3000):
    """Move one axis by 'distance' mm (relative). Positive = away from origin."""
    set_relative(ser)
    send(ser, f"G0 {axis}{distance:+.2f} F{feed}")
    set_absolute(ser)                 # always return to absolute mode


def home(ser, axes=""):
    """Home all axes, or pass 'X', 'Y', 'Z' to home individual axes."""
    cmd = f"G28 {axes}".strip()
    send(ser, cmd, timeout=120)       # homing can be slow


def print_menu():
    print(f"""
╔══════════════════════════════════════════╗
║        3D PRINTER MOVEMENT CONTROL       ║
╠══════════════════════════════════════════╣
║  BED (Y-axis)                           ║
║   f  →  Bed forward  (+Y)              ║
║   b  →  Bed backward (-Y)              ║
║                                          ║
║  NOZZLE X-axis                           ║
║   l  →  Left  (-X)                     ║
║   r  →  Right (+X)                     ║
║                                          ║
║  Z-axis (gantry / nozzle height)         ║
║   u  →  Up    (+Z)                     ║
║   d  →  Down  (-Z)                     ║
║                                          ║
║  EXTRUDER                                ║
║   e  →  Extrude  (+E)                  ║
║   t  →  Retract  (-E)                  ║
║                                          ║
║  STEP SIZE  (current: {CURRENT_STEP:5.1f} mm)         ║
║   1  →  {STEP_SMALL} mm                            ║
║   2  →  {STEP_MEDIUM} mm                            ║
║   3  →  {STEP_LARGE} mm                           ║
║                                          ║
║  OTHER                                   ║
║   p  →  Print current position          ║
║   h  →  Home all axes                  ║
║   q  →  Quit                           ║
╚══════════════════════════════════════════╝
""")


def main():
    global CURRENT_STEP

    print("Connecting to printer …")
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=TIMEOUT)
    except serial.SerialException as e:
        print(f"✗ Cannot open {SERIAL_PORT}: {e}")
        sys.exit(1)

    time.sleep(2)                       # wait for Marlin banner
    ser.reset_input_buffer()

    # Make sure we start in absolute mode
    set_absolute(ser)

    print_menu()

    while True:
        try:
            cmd = input("Command: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if cmd == "q":
            break

        elif cmd == "p":
            pos = get_position(ser)
            if pos:
                print(f"  X={pos.get('X','?')} mm  "
                      f"Y={pos.get('Y','?')} mm  "
                      f"Z={pos.get('Z','?')} mm  "
                      f"E={pos.get('E','?')} mm")
            else:
                print("  ⚠ Could not read position")

        elif cmd == "h":
            print("  Homing all axes …")
            home(ser)

        elif cmd == "1":
            CURRENT_STEP = STEP_SMALL
            print(f"  Step size → {CURRENT_STEP} mm")

        elif cmd == "2":
            CURRENT_STEP = STEP_MEDIUM
            print(f"  Step size → {CURRENT_STEP} mm")

        elif cmd == "3":
            CURRENT_STEP = STEP_LARGE
            print(f"  Step size → {CURRENT_STEP} mm")

        # ── Bed / Y ──────────────────────────────────
        elif cmd == "f":
            print(f"  Bed forward  +{CURRENT_STEP} mm (Y+)")
            move(ser, "Y", +CURRENT_STEP)

        elif cmd == "b":
            print(f"  Bed backward -{CURRENT_STEP} mm (Y-)")
            move(ser, "Y", -CURRENT_STEP)

        # ── X ────────────────────────────────────────
        elif cmd == "r":
            print(f"  Right +{CURRENT_STEP} mm (X+)")
            move(ser, "X", +CURRENT_STEP)

        elif cmd == "l":
            print(f"  Left  -{CURRENT_STEP} mm (X-)")
            move(ser, "X", -CURRENT_STEP)

        # ── Z ────────────────────────────────────────
        elif cmd == "u":
            print(f"  Up    +{CURRENT_STEP} mm (Z+)")
            move(ser, "Z", +CURRENT_STEP, feed=1000)   # Z is slower

        elif cmd == "d":
            print(f"  Down  -{CURRENT_STEP} mm (Z-)")
            move(ser, "Z", -CURRENT_STEP, feed=1000)

        # ── Extruder / E ─────────────────────────────
        elif cmd == "e":
            print(f"  Extrude +{CURRENT_STEP} mm (E+)")
            move(ser, "E", +CURRENT_STEP, feed=300)    # extruder is slow

        elif cmd == "t":
            print(f"  Retract -{CURRENT_STEP} mm (E-)")
            move(ser, "E", -CURRENT_STEP, feed=300)

        elif cmd == "m":
            print_menu()

        else:
            print("  Unknown command. Type 'm' to see the menu.")

    ser.close()
    print("Port closed. Goodbye!")


if __name__ == "__main__":
    main()