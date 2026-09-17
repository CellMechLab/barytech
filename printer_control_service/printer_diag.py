#!/usr/bin/env python3
"""
printer_diag.py — standalone firmware diagnostic for the Prusa Core One.

Run this on the Pi with nothing else talking to the serial port
(stop the FastAPI service first, or it will fight for /dev/ttyACM*).

    python3 printer_diag.py
    python3 printer_diag.py --port /dev/ttyACM1
    python3 printer_diag.py --g92-test        # also probe G92 behaviour

What it answers:
  * Which firmware fork/version is this really (M115)?
  * Are the printer's own endstops alive (M119)?
  * What does the firmware think the position is (M114), and does that
    match what G92 told it?
  * Are soft endstops on or off, and does M211 report state (M211 alone)?

Nothing here moves the machine, EXCEPT the optional --g92-test, which
only issues G92 (a relabel, no motion) and then reads back position.
"""

import argparse
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial not installed:  pip3 install pyserial")


DEFAULT_PORTS = ["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0"]
BAUD = 230400


def drain(ser, settle=0.3):
    """Read and discard whatever is sitting in the buffer."""
    time.sleep(settle)
    ser.reset_input_buffer()


def send(ser, cmd, timeout=6.0, quiet=False):
    """
    Send one G-code line and collect every response line until 'ok'
    (or timeout). Returns the list of raw lines.

    Unlike the service's _send_locked, this keeps NON-ok lines too —
    that's the whole point here, since M115/M119 answer with many
    lines before the final ok.
    """
    ser.reset_input_buffer()
    ser.write((cmd.strip() + "\n").encode())
    if not quiet:
        print(f"\n>>> {cmd}")

    lines = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = ser.readline().decode(errors="ignore").strip()
        if not raw:
            continue
        lines.append(raw)
        if not quiet:
            print(f"    {raw}")
        if raw.startswith("ok") or raw.startswith("Error") or raw.startswith("!!"):
            break
    else:
        if not quiet:
            print(f"    [TIMEOUT after {timeout}s — no 'ok' received]")
    return lines


def open_port(port):
    print(f"Opening {port} @ {BAUD} ...")
    ser = serial.Serial(port, BAUD, timeout=2.0)
    # Buddy/Marlin spits a greeting banner; give it room then flush.
    time.sleep(3)
    drain(ser)
    return ser


def autodetect():
    for p in DEFAULT_PORTS:
        try:
            ser = open_port(p)
            probe = send(ser, "M115", timeout=5.0, quiet=True)
            if any("FIRMWARE_NAME" in l or l.startswith("ok") for l in probe):
                print(f"  -> responded like a printer on {p}")
                return ser
            ser.close()
        except Exception as exc:
            print(f"  {p}: {exc}")
    return None


def section(title):
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="serial port; autodetects if omitted")
    ap.add_argument("--g92-test", action="store_true",
                    help="probe whether G92 actually rebases native position")
    args = ap.parse_args()

    if args.port:
        ser = open_port(args.port)
    else:
        ser = autodetect()
        if ser is None:
            sys.exit("No printer found on " + ", ".join(DEFAULT_PORTS))

    try:
        section("M115 — firmware identity and capabilities")
        print("Look for: FIRMWARE_NAME (Buddy vs Marlin), version, and the")
        print("Cap: lines listing what this fork actually supports.")
        send(ser, "M115", timeout=8.0)

        section("M119 — endstop states")
        print("This is the key one. If the printer's OWN endstops report")
        print("real states (open/TRIGGERED) rather than being absent, then")
        print("G28 has hardware to work with. If everything reads 'open'")
        print("even at a physical limit, its endstops aren't usable.")
        send(ser, "M119", timeout=8.0)

        section("M114 — current position as the firmware reports it")
        print("Compare this to the printer's touchscreen reading right now.")
        print("If they DISAGREE, G92 shifted only the G-code/workspace")
        print("coordinate and left native position untouched — which is")
        print("exactly the failure mode we're chasing.")
        send(ser, "M114")

        section("M114 R / D — native vs logical position (if supported)")
        print("M114 R asks for the machine/native position specifically.")
        print("If this differs from plain M114, that difference IS the")
        print("workspace offset G92 created.")
        send(ser, "M114 R")
        send(ser, "M114 D")

        section("M211 — soft endstop state readback")
        print("M211 with no argument should report whether soft endstops")
        print("are on/off and the min/max it is enforcing. If it reports")
        print("nothing useful, this fork may accept 'ok' for M211 S0")
        print("without the setting actually taking effect.")
        send(ser, "M211")

        section("M503 — full firmware settings dump")
        print("Long. Search the output for travel limits / max pos values.")
        send(ser, "M503", timeout=15.0)

        if args.g92_test:
            section("G92 BEHAVIOUR PROBE  (no motion — relabel only)")
            print("Reads position, applies G92 Y185, reads back, then")
            print("re-reads native position. This tells us definitively")
            print("whether G92 moves the native reference or only the")
            print("workspace offset on this firmware.")
            print("\n--- before ---")
            send(ser, "M114")
            send(ser, "M114 R")
            print("\n--- applying G92 Y185 ---")
            send(ser, "G92 Y185")
            print("\n--- after ---")
            send(ser, "M114")
            send(ser, "M114 R")
            print("\nINTERPRETATION:")
            print("  * If M114 changed to Y:185 but M114 R did NOT change,")
            print("    G92 is only a workspace offset here. Soft endstops")
            print("    and the touchscreen will keep using native position,")
            print("    and no G92 can widen your travel.")
            print("  * If BOTH changed, G92 does rebase native position and")
            print("    the travel limit is coming from somewhere else.")

        section("WHAT TO DO WITH THIS")
        print("Paste the M115, M119 and M211 sections back into the chat.")
        print("The M119 result decides the path:")
        print("  - endstops report real states -> try 'G28 Y' for a true home")
        print("  - endstops dead/absent        -> Configuration.h + reflash")

    finally:
        ser.close()
        print("\nPort closed.")


if __name__ == "__main__":
    main()