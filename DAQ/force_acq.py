# force_acq.py
# ---------- FORCE via SPI (Pi) — threadable, GUI-ready ----------


import os
import RPi.GPIO as GPIO
import spidev, struct, time
import numpy as np
import threading, queue
import math
# ======= User-tweakables =======
SPI_BUS = 0
SPI_DEV = 0
SPI_SPEED_HZ = 100000

DATA_READY = 17
DRDY_ACTIVE_HIGH = True  # If your DRDY is active-low, set this to False

FORCE_FEED = "/tmp/force_feed.txt"

# ======= Your ADC + calibration constants (unchanged) =======
ADC_BITS  = 16
ADC_VREF  = 3.3
ADC_GAIN  = 1.0
COUNTS_TO_VOLTS = (ADC_VREF / ((1 << ADC_BITS) - 1)) / max(ADC_GAIN, 1e-12)
# ===== Aurora 406B calibration  =====
AURORA_BASELINE_V   = 0.004         # zero-offset voltage (unloaded)
AURORA_SCALE_MN_PER_V = 0.69        # mN per volt (≈ from 100 µL test @ ×10 gain)
AURORA_SCALE_N_PER_V  = AURORA_SCALE_MN_PER_V * 1e-3  # N per volt
# ===== C-Sense calibration =====

CSENSE_SENS_N_PER_V = 20e-6         

# Convert to nN per Volt (1 N = 1e9 nN)
CSENSE_SENS_NN_PER_V = CSENSE_SENS_N_PER_V * 1e9   # nN per Volt
 # mN per Volt

GAIN_SWITCH        = 1
SENS_N_PER_V_X1    = 5.0e-5
SENS_N_PER_V       = SENS_N_PER_V_X1 / GAIN_SWITCH

TARE_METHOD = "auto"
TARE_VOLTS  = 0.300

# ======= Frame/layout (unchanged) =======
BUFFER_SIZE = 8
SPI_HEADER_BYTES = 12
SPI_FRAME_BYTES  = SPI_HEADER_BYTES + 2*BUFFER_SIZE
MAGIC = 0xA5F01234

# ======= Sync fit memory (unchanged) =======
WINDOW = 4000

# ========== small helpers ==========
def _pin_is_active():
    return (GPIO.input(DATA_READY) == GPIO.HIGH) if DRDY_ACTIVE_HIGH else (GPIO.input(DATA_READY) == GPIO.LOW)

def _wait_frame_ready(timeout_s=1.0):
    t0 = time.monotonic()
    if _pin_is_active():
        return True
    while not _pin_is_active():
        if time.monotonic() - t0 > timeout_s:
            return False
    return True

def _wait_frame_end(timeout_s=0.02):
    t0 = time.monotonic()
    while _pin_is_active():
        if time.monotonic() - t0 > timeout_s:
            break

def _drain_one_frame(spi):
    try:
        _ = spi.xfer2([0x00] * SPI_FRAME_BYTES)
    except Exception:
        pass

def lsq_offset_drift(pairs):
    n = len(pairs)
    if n < 3:
        return (pairs[-1][1] - pairs[-1][0]) if n else 0.0, 1.0
    Sx = Sy = Sxx = Sxy = 0.0
    for s, p in pairs:
        Sx += s; Sy += p; Sxx += s*s; Sxy += s*p
    den = (n*Sxx - Sx*Sx)
    if abs(den) < 1e-18:
        return (pairs[-1][1] - pairs[-1][0]), 1.0
    m = (n*Sxy - Sx*Sy)/den
    b = (Sy - m*Sx)/n
    return b, m

# ========== worker ==========
class ForceWorker(threading.Thread):
    """
    Command queue strings: 'start' | 'stop' | 'quit'
    UI text lines posted to uiq.
    """
    def __init__(self, cmdq: "queue.Queue[str]", uiq: "queue.Queue[str]"):
        super().__init__(daemon=True)
        self.cmdq = cmdq
        self.uiq = uiq
        self.running = False
        self.stop_flag = False

    def _open_spi(self):
        spi = spidev.SpiDev()
        spi.open(SPI_BUS, SPI_DEV)
        spi.max_speed_hz = SPI_SPEED_HZ
        spi.mode = 0
        spi.bits_per_word = 8
        return spi

    def run(self):
        # GPIO
        GPIO.setmode(GPIO.BCM)
        pud = GPIO.PUD_DOWN if DRDY_ACTIVE_HIGH else GPIO.PUD_UP
        GPIO.setup(DATA_READY, GPIO.IN, pull_up_down=pud)

        # SPI
        spi = None
        try:
            spi = self._open_spi()
        except Exception as e:
            self.uiq.put(f"Force: SPI open failed: {e}")
            return

        # file
        try:
            ff = open(FORCE_FEED, "w", buffering=1)
        except Exception as e:
            self.uiq.put(f"Force: cannot open {FORCE_FEED}: {e}")
            ff = None

        self.uiq.put(f"Force: ready. SPI /dev/spidev{SPI_BUS}.{SPI_DEV} @ {SPI_SPEED_HZ} Hz, "
                     f"DRDY pin {DATA_READY} {'active-high' if DRDY_ACTIVE_HIGH else 'active-low'}.")

       
        last_fid = None
        last_t_us = None
        sync_buffer = []
        drift = 1.0

        frames = 0
        last_heartbeat = time.monotonic()

        try:
            while not self.stop_flag:
                # commands
                try:
                    while True:
                        k = self.cmdq.get_nowait()
                        if k == "start":
                            self.running = True
                            self.uiq.put("Force: acquisition started.")
                        elif k == "stop":
                            self.running = False
                            self.uiq.put("Force: acquisition stopped.")
                        elif k == "quit":
                            self.stop_flag = True
                            break
                except queue.Empty:
                    pass
                if self.stop_flag:
                    break

                if not self.running:
                    if time.monotonic() - last_heartbeat > 2.0:
                        self.uiq.put("Force: idle.")
                        last_heartbeat = time.monotonic()
                    time.sleep(0.05)
                    continue

                # =======================
                # BEGIN ORIGINAL CORE (unchanged)
                # =======================
                if not _wait_frame_ready(1.0):
                    if _pin_is_active():
                        _drain_one_frame(spi)
                    # end original behavior: just continue
                    # (we also emit a heartbeat above)
                    continue

                time.sleep(0.0001)  # 100 µs to let STM32 feed SPI FIFO

               
                now_pi_before = time.monotonic()

                raw = spi.xfer2([0x00] * SPI_FRAME_BYTES)
                if len(raw) != SPI_FRAME_BYTES:
                    _wait_frame_end()
                    continue

                b = bytes(raw)
                magic, fid, t_us = struct.unpack_from('<III', b, 0)
                if magic != MAGIC:
                    if _pin_is_active():
                        _drain_one_frame(spi)
                    continue

                # frame continuity (optional)
                if (last_fid is not None) and (fid != (last_fid + 1)):
                    # we also print to the UI outside the core
                    pass
                last_fid = fid

                # map STM32 time -> Pi time with drift+offset
                t_stm = t_us * 1e-6
                sync_buffer.append((t_stm, now_pi_before))
                if len(sync_buffer) > WINDOW:
                    sync_buffer.pop(0)

                offset, drift = lsq_offset_drift(sync_buffer)
                t_pi_frame_end = drift*t_stm + offset  
                # -------- unpack samples as SIGNED int16 --------
                samples = list(struct.unpack_from('<' + 'H'*BUFFER_SIZE, b, SPI_HEADER_BYTES))

                if last_t_us is None or t_us <= last_t_us:
                    per_sample_times = np.full(BUFFER_SIZE, t_pi_frame_end, float)
                else:
                    dt_frame_s = (t_us - last_t_us) / 1e6
                    per_sample_times = np.linspace(
                        t_pi_frame_end - dt_frame_s,
                        t_pi_frame_end,
                        BUFFER_SIZE
                    )

                last_t_us = t_us


                if ff is not None:
                    for t_samp, x in zip(per_sample_times, samples):
                        # Convert raw ADC to volts
                       # Convert raw ADC to volts
                        factor = 10**2
                        volts = x * COUNTS_TO_VOLTS
                       # volts = math.trunc(volts * factor) / factor  # round to 2 decimals

                        # Convert volts -> force
                        force_nN = volts * CSENSE_SENS_NN_PER_V

                        # Layout:
                        #   col1 = time (s)
                        #   col2 = raw ADC counts
                        #   col3 = volts
                        #   col4 = force (mN)
                        ff.write(f"{t_samp:.9f} {int(x)} {volts:.6f} {force_nN:.3f}\n")

                _wait_frame_end()
                # =======================
                # END ORIGINAL CORE
                # =======================

                frames += 1
                if frames % 50 == 0:
                    self.uiq.put(f"Force: fid={fid} s0={samples[0]}")
                # also surface FID jumps
                if (frames % 50 == 0) and (last_fid is not None):
                    pass

        finally:
            try:
                if spi: spi.close()
            except: pass
            try:
                GPIO.cleanup(DATA_READY)  # only our pin
            except: pass
            try:
                if ff: ff.close()
            except: pass
            self.uiq.put(f"Force: thread exit. Frames={frames}")

# ---------- standalone quick test ----------
if __name__ == "__main__":
    cq, uq = queue.Queue(), queue.Queue()
    w = ForceWorker(cq, uq); w.start()
    cq.put("start")
    try:
        while True:
            try:
                print(uq.get(timeout=0.5))
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        cq.put("quit")
