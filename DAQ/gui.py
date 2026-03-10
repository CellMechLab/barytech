# gui.py
# Indenter GUI (compact + scrollable)
# - Z via MotorWorker (ximc)
# - Force via ForceWorker (SPI)
# - XY stage via KimClient (Windows KIM bridge)
#


import os, time, queue, tkinter as tk
from tkinter import ttk, messagebox
from collections import deque
import threading, traceback
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import subprocess, sys, signal, shlex

FORCE_START_THRESHOLD = 0.0

# --- Camera deps (OpenCV) ---
try:
    import cv2
    _CV2_OK = True
except Exception:
    _CV2_OK = False

matplotlib.use("TkAgg")
matplotlib.rcParams['toolbar'] = 'toolbar2'   # show pan/zoom/save tools
plt.ion()  # interactive mode

from motor_control import MotorWorker
from force_acq     import ForceWorker
from kim101_client import KimClient

EXPORT_DIR = os.path.expanduser("~/indents")  # change if you like

def _ensure_dir(p):
    try:
        os.makedirs(p, exist_ok=True)
    except Exception:
        pass

# Feeds
FORCE_FILE = "/tmp/force_feed.txt"  # (time_s, counts[, volts, mN])
MOTOR_FILE = "/tmp/motor_feed.txt"  # (time_s, disp_mm)
# ----- Simple F–Disp plotting prefs -----
SIMPLE_DISP_OFFSET_UM = 0.0
EXTRAPOLATE_LEFT_UM   = 0.0
EXTRAPOLATE_FIT_SAMPLES = 200

# ---- Force ceiling for plotting (mN). 
MAX_FORCE_PLOT_MN = 0.40

# Conversion used in motor_ctrl.py so GUI can back-compute steps from mm:
STEP_TO_MM = 0.00008333

# --- Z motion timing (coarse; adjust to your rig) ---
Z_APPROX_SPEED_STEPS_PER_S = 1800.0
Z_WAIT_EXTRA_S              = 0.05

UNI_LOGO    = "uofg.jpg"
FUNDER_LOGO = ""
# ----- Simple F–Disp plotting prefs -----
SIMPLE_DISP_OFFSET_UM = 0.0   
EXTRAPOLATE_LEFT_UM   = 0.0   
EXTRAPOLATE_FIT_SAMPLES = 200 

try:
    from PIL import Image, ImageTk
    _PIL_OK = True
except Exception:
    _PIL_OK = False

def _load_logo(path: str, max_h=44):
    if not path or not os.path.exists(path): return None
    try:
        if _PIL_OK:
            img = Image.open("schaefer.png")  
            w, h = img.size
            if h > max_h:
                s = max_h/float(h)
                img = img.resize((max(1,int(w*s)), max(1,int(h*s))), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        if path.lower().endswith((".png",".gif")):
            im = tk.PhotoImage(file=path)
            h = im.height()
            if h>max_h:
                f = max(1, h//max_h)
                im = im.subsample(f,f)
            return im
    except Exception:
        pass
    return None

class ScrollableFrame(ttk.Frame):
    def __init__(self, master, *a, **k):
        super().__init__(master, *a, **k)
        self.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.content = ttk.Frame(self.canvas)
        self.win = self.canvas.create_window((0,0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.win, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-3,"units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(+3,"units"))
    def _wheel(self, e): self.canvas.yview_scroll(int(-1*(e.delta/120)), "units")

class App(tk.Tk):
    def __init__(self, uri: str = "", kim_endpoint: str = ""):
        super().__init__()
        self.title("Nanoindenter Control")
        self._set_scaling()

        # workers
        self.uiq         = queue.Queue()
        self.force_cmdq  = queue.Queue()
        self.motor_cmdq  = queue.Queue()
        self.force       = ForceWorker(self.force_cmdq, self.uiq); self.force.start()
        self.motor       = MotorWorker(self.motor_cmdq, self.uiq, default_uri=uri); self.motor.start()

        # stage client
        self.stage       = KimClient(endpoint=kim_endpoint)
        self._stage_enabled_once = False

        # log buffer + plot queue
        self._logbuf = deque(maxlen=8000)
        self._plot_requests = deque(maxlen=64)

        # header
        self._header_imgs = []
        self._build_header()

        # tabs
        self.nb = ttk.Notebook(self); self.nb.pack(fill="both", expand=True)
        self.ctrl_sf   = ScrollableFrame(self.nb)
        self.status_sf = ScrollableFrame(self.nb)
        self.data_sf   = ScrollableFrame(self.nb)
        self.nb.add(self.ctrl_sf,   text="Control")
        self.nb.add(self.status_sf, text="Status")
        self.stream_sf = ScrollableFrame(self.nb)
        self.nb.add(self.stream_sf, text="Streaming")
        self.cam_sf = ScrollableFrame(self.nb)
        self.nb.add(self.cam_sf, text="Camera")

        # camera state
        self._camera_cap = None
        self._camera_running = False
        self._cam_job = None
        self._cam_imgtk = None  # prevent GC

        # publisher process handle + stdout reader thread
        self._publisher_proc = None
        self._publisher_reader = None

        # build
        self._build_control(self.ctrl_sf.content, uri)
        self._build_status(self.status_sf.content)
        self._build_data(self.data_sf.content)
        self._build_streaming(self.stream_sf.content)
        self._build_camera(self.cam_sf.content)

        # pumps
        self.after(80, self._pump)
        self.after(120, self._pump_plots)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # auto-connect Z
        if uri and not uri.startswith("<"):
            self.after(200, lambda: self.motor_cmdq.put(("connect", uri)))

        self._run_stop = threading.Event()

    # -------- sizing
    def _set_scaling(self):
        try:
            w = self.winfo_screenwidth(); h = self.winfo_screenheight()
        except Exception:
            w, h = 1024, 600
        try:
            if h < 800: self.tk.call('tk','scaling',0.85)
            if h < 700: self.tk.call('tk','scaling',0.80)
        except Exception:
            pass
        try: self.state("zoomed")
        except Exception: self.attributes("-zoomed", True)
        self.geometry(f"{w}x{h}+0+0")

    # -------- header
    def _build_header(self):
        hdr = ttk.Frame(self); hdr.pack(fill="x", padx=8, pady=(8,4)); hdr.columnconfigure(3, weight=1)
        uni   = _load_logo(UNI_LOGO, max_h=44)
        fund  = _load_logo(FUNDER_LOGO, max_h=44)
        col=0
        if uni:  ttk.Label(hdr,image=uni ).grid(row=0,column=col,sticky="w",padx=(2,10)); self._header_imgs.append(uni ); col+=1
        if fund: ttk.Label(hdr,image=fund).grid(row=0,column=col,sticky="w",padx=(2,10)); self._header_imgs.append(fund); col+=1
        ttk.Label(hdr, text="Nanoindenter Control Panel", font=("TkDefaultFont", 14, "bold")).grid(row=0, column=2, sticky="w")

        right = ttk.Frame(hdr); right.grid(row=0,column=3,sticky="e")
        ttk.Label(right, text="Stage:").grid(row=0,column=0,sticky="e",padx=(0,6))
        self.stage_light = tk.Canvas(right, width=14, height=14, highlightthickness=0); self.stage_light.grid(row=0,column=1)
        ttk.Button(right, text="Ping", command=self._ping_stage).grid(row=0,column=2,padx=(6,0))
        self._set_stage_light("unknown")

    def _set_stage_light(self, state: str):
        self.stage_light.delete("all")
        color = {"ok":"#11c000","bad":"#cc0000","unknown":"#bbbbbb"}.get(state,"#bbbbbb")
        self.stage_light.create_oval(2,2,12,12, fill=color, outline=color)

    def _ping_stage(self):
        def work():
            if not self.stage.configured():
                self._log("Stage ping: endpoint not set (use --kim http://IP:5005)")
                self.after(0, lambda: self._set_stage_light("bad"))
                return
            ok, info = self.stage.info()
            self._log(f"Stage ping: {'OK' if ok else 'FAIL'} — {info}")
            self.after(0, lambda: self._set_stage_light('ok' if ok else 'bad'))
        self._bg(work)

    # -------- control UI
    def _build_control(self, root, uri_hint: str):
        pad = {"padx":8,"pady":6}

        # Z device
        dev = ttk.LabelFrame(root, text="Z Device"); dev.grid(row=0,column=0,sticky="ew",**pad)
        for c in (0,1,2): dev.columnconfigure(c, weight=(1 if c==1 else 0))
        ttk.Label(dev, text="XIMC URI:").grid(row=0,column=0,sticky="e")
        self.uri_var = tk.StringVar(value=(uri_hint or os.environ.get("XIMC_URI") or ""))
        if not self.uri_var.get(): self.uri_var.set("<e.g. xi-com:///dev/ttyACM0>")
        ttk.Entry(dev, textvariable=self.uri_var).grid(row=0,column=1,sticky="ew",padx=6)
        ttk.Button(dev, text="Connect Z Motor", command=self._connect_motor).grid(row=0,column=2,sticky="w")

        # Z motor group
        zf = ttk.LabelFrame(root, text="Z Motor (XIMC)"); zf.grid(row=1,column=0,sticky="ew",**pad)
        for c in range(6): zf.columnconfigure(c, weight=(1 if c in (1,3,4,5) else 0))
        ttk.Label(zf,text="Jog steps:").grid(row=0,column=0,sticky="e")
        self.jog_var = tk.StringVar(value="2000")  # positive magnitude
        ttk.Entry(zf,textvariable=self.jog_var,width=10).grid(row=0,column=1,sticky="w",padx=6)
        ttk.Button(zf,text="Jog Down",command=lambda:self._jog("down")).grid(row=0,column=2)
        ttk.Button(zf,text="Jog Up",  command=lambda:self._jog("up")).grid(row=0,column=3)
        ttk.Label(zf,text="Speed:").grid(row=1,column=0,sticky="e")
        self.speed_var = tk.StringVar(value="500")
        ttk.Entry(zf,textvariable=self.speed_var,width=10).grid(row=1,column=1,sticky="w",padx=6)
        ttk.Button(zf,text="Set Speed",command=self._set_speed).grid(row=1,column=2)
        ttk.Button(zf,text="Stop",     command=lambda:self.motor_cmdq.put(("stop",None))).grid(row=1,column=3)
        ttk.Button(zf,text="E-STOP",   command=lambda:self.motor_cmdq.put(("estop",None))).grid(row=1,column=4)

        hold = ttk.LabelFrame(zf, text="Continuous (Hold Buttons)")
        hold.grid(row=2,column=0,columnspan=6,sticky="ew",pady=(4,0))
        btn_dn = ttk.Button(hold,text="Hold DOWN"); btn_up = ttk.Button(hold,text="Hold UP")
        btn_dn.grid(row=0,column=0,padx=6,pady=6); btn_up.grid(row=0,column=1,padx=6,pady=6)
        btn_dn.bind("<ButtonPress-1>",  lambda e: self.motor_cmdq.put(("cont_move","down")))
        btn_dn.bind("<ButtonRelease-1>",lambda e: self.motor_cmdq.put(("stop",None)))
        btn_up.bind("<ButtonPress-1>",  lambda e: self.motor_cmdq.put(("cont_move","up")))
        btn_up.bind("<ButtonRelease-1>",lambda e: self.motor_cmdq.put(("stop",None)))

        # Force group
        ff = ttk.LabelFrame(root, text="Force Acquisition (SPI)")
        ff.grid(row=2,column=0,sticky="ew",**pad)
        for c in range(4): ff.columnconfigure(c, weight=(1 if c==3 else 0))
        ttk.Button(ff,text="Start",command=lambda:self.force_cmdq.put("start")).grid(row=0,column=0,padx=6,pady=6)
        ttk.Button(ff,text="Stop", command=lambda:self.force_cmdq.put("stop")).grid(row=0,column=1,padx=6,pady=6)
        ttk.Button(ff,text="F–Disp (nN vs µm)", command=self._request_plot_force_disp).grid(row=1,column=0,padx=6,pady=(0,6))
        ttk.Button(ff,text="V/Counts vs Steps",  command=self._request_plot_counts_steps).grid(row=1,column=1,padx=6,pady=(0,6))
        # Show pre-contact (negative displacement) toggle
        self.show_precontact = tk.BooleanVar(value=False)
        ttk.Checkbutton(ff, text="Show pre-contact (negative disp)",
                        variable=self.show_precontact).grid(row=1, column=2, padx=6, pady=(0,6), sticky="w")
        ttk.Button(ff, text="F–Disp (simple)", command=lambda: self._plot_requests.append(
            lambda: self._plot_force_disp_simple_mainthread(offset_um=SIMPLE_DISP_OFFSET_UM))
        ).grid(row=1, column=2, padx=6, pady=(0,6))


        # XY Stage
        sf = ttk.LabelFrame(root, text="XY Stage (KIM101)")
        sf.grid(row=3,column=0,sticky="ew",**pad)
        for c in range(10): sf.columnconfigure(c, weight=(1 if c in (1,3,5,7,9) else 0))
        ttk.Button(sf,text="Ping",                 command=self._ping_stage).grid(row=0,column=0,padx=6,pady=6,sticky="w")
        ttk.Button(sf,text="Enable",               command=self._stage_enable).grid(row=0,column=1,padx=6,pady=6,sticky="w")
        ttk.Button(sf,text="Set Home (zero X&Y)",  command=self._stage_set_home).grid(row=0,column=2,padx=6,pady=6,sticky="w")
        ttk.Button(sf,text="Go Home (move 0,0)",   command=self._stage_go_home).grid(row=0,column=3,padx=6,pady=6,sticky="w")

        ttk.Label(sf,text="Nudge X:").grid(row=1,column=0,sticky="e")
        ttk.Button(sf,text="X -100",command=lambda:self._xy_with_guard(lambda: self._stage_nudge_delta(1,-100))).grid(row=1,column=1,padx=6,pady=6)
        ttk.Button(sf,text="X +100",command=lambda:self._xy_with_guard(lambda: self._stage_nudge_delta(1,+100))).grid(row=1,column=2,padx=6,pady=6)
        ttk.Label(sf,text="Nudge Y:").grid(row=1,column=3,sticky="e")
        ttk.Button(sf,text="Y -100",command=lambda:self._xy_with_guard(lambda: self._stage_nudge_delta(2,-100))).grid(row=1,column=4,padx=6,pady=6)
        ttk.Button(sf,text="Y +100",command=lambda:self._xy_with_guard(lambda: self._stage_nudge_delta(2,+100))).grid(row=1,column=5,padx=6,pady=6)

        ttk.Label(sf,text="Move X to (steps):").grid(row=2,column=0,sticky="e")
        self.x_target = tk.StringVar(value="0")
        ttk.Entry(sf,textvariable=self.x_target,width=10).grid(row=2,column=1,sticky="w")
        ttk.Button(sf,text="Move X",command=lambda:self._xy_with_guard(self._stage_move_x)).grid(row=2,column=2,padx=6,pady=6)

        ttk.Label(sf,text="Move Y to (steps):").grid(row=2,column=3,sticky="e")
        self.y_target = tk.StringVar(value="0")
        ttk.Entry(sf,textvariable=self.y_target,width=10).grid(row=2,column=4,sticky="w")
        ttk.Button(sf,text="Move Y",command=lambda:self._xy_with_guard(self._stage_move_y)).grid(row=2,column=5,padx=6,pady=6)

        ttk.Button(sf,text="Move XY to targets",command=lambda:self._xy_with_guard(self._stage_move_xy)).grid(row=2,column=6,padx=6,pady=6)

        # ---- Single Indentation
        demo = ttk.LabelFrame(root, text="Demo: Single Indentation (steps)")
        demo.grid(row=4, column=0, sticky="ew", **pad)
        for c in range(8): demo.columnconfigure(c, weight=(1 if c in (1,3,5,7) else 0))
        ttk.Label(demo, text="Approach (steps):").grid(row=0, column=0, sticky="e")
        self.si_approach = tk.StringVar(value="2000")
        ttk.Entry(demo, textvariable=self.si_approach, width=10).grid(row=0, column=1, sticky="w")
        ttk.Label(demo, text="Hold (ms):").grid(row=0, column=2, sticky="e")
        self.si_hold_ms = tk.StringVar(value="2000")
        ttk.Entry(demo, textvariable=self.si_hold_ms, width=10).grid(row=0, column=3, sticky="w")
        ttk.Label(demo, text="Retract (steps):").grid(row=0, column=4, sticky="e")
        self.si_retract = tk.StringVar(value="2000")
        ttk.Entry(demo, textvariable=self.si_retract, width=10).grid(row=0, column=5, sticky="w")
        self.si_autoplot = tk.BooleanVar(value=True)
        ttk.Checkbutton(demo, text="Auto-plot", variable=self.si_autoplot).grid(row=0, column=6, sticky="w")
        ttk.Button(demo, text="Run Single Indentation", command=self._run_single_indent_bg).grid(row=0, column=7, padx=6, pady=6)

        # ---- Matrix Scan
        grid = ttk.LabelFrame(root, text="Demo: Matrix Scan")
        grid.grid(row=5, column=0, sticky="ew", **pad)
        for c in range(18): grid.columnconfigure(c, weight=(1 if c in (1,3,5,7,9,11,13,15,17) else 0))

        ttk.Label(grid, text="Start X (req):").grid(row=0, column=0, sticky="e")
        self.ms_x0 = tk.StringVar(value=""); ttk.Entry(grid, textvariable=self.ms_x0, width=10).grid(row=0, column=1, sticky="w")
        ttk.Label(grid, text="Start Y (req):").grid(row=0, column=2, sticky="e")
        self.ms_y0 = tk.StringVar(value=""); ttk.Entry(grid, textvariable=self.ms_y0, width=10).grid(row=0, column=3, sticky="w")

        ttk.Label(grid, text="ΔX:").grid(row=0, column=4, sticky="e")
        self.ms_dx = tk.StringVar(value="1000"); ttk.Entry(grid, textvariable=self.ms_dx, width=10).grid(row=0, column=5, sticky="w")
        ttk.Label(grid, text="ΔY:").grid(row=0, column=6, sticky="e")
        self.ms_dy = tk.StringVar(value="1000"); ttk.Entry(grid, textvariable=self.ms_dy, width=10).grid(row=0, column=7, sticky="w")

        ttk.Label(grid, text="Nx:").grid(row=0, column=8, sticky="e")
        self.ms_nx = tk.StringVar(value="3"); ttk.Entry(grid, textvariable=self.ms_nx, width=6).grid(row=0, column=9, sticky="w")
        ttk.Label(grid, text="Ny:").grid(row=0, column=10, sticky="e")
        self.ms_ny = tk.StringVar(value="3"); ttk.Entry(grid, textvariable=self.ms_ny, width=6).grid(row=0, column=11, sticky="w")

        ttk.Label(grid, text="Settle (ms):").grid(row=1, column=0, sticky="e")
        self.ms_settle = tk.StringVar(value="200"); ttk.Entry(grid, textvariable=self.ms_settle, width=10).grid(row=1, column=1, sticky="w")

        ttk.Label(grid, text="Matrix Z → Appr:").grid(row=1, column=2, sticky="e")
        self.ms_appr = tk.StringVar(value="2000"); ttk.Entry(grid, textvariable=self.ms_appr, width=8).grid(row=1, column=3, sticky="w")
        ttk.Label(grid, text="Hold (ms):").grid(row=1, column=4, sticky="e")
        self.ms_hold = tk.StringVar(value="2000"); ttk.Entry(grid, textvariable=self.ms_hold, width=8).grid(row=1, column=5, sticky="w")
        ttk.Label(grid, text="Retract:").grid(row=1, column=6, sticky="e")
        self.ms_retr = tk.StringVar(value="2000"); ttk.Entry(grid, textvariable=self.ms_retr, width=8).grid(row=1, column=7, sticky="w")

        self.ms_use_custom_z = tk.BooleanVar(value=True)
        ttk.Checkbutton(grid, text="Use these Z settings", variable=self.ms_use_custom_z).grid(row=1, column=8, columnspan=3, sticky="w")

        self.ms_autoplot_each = tk.BooleanVar(value=False)
        ttk.Checkbutton(grid, text="Auto-plot each point", variable=self.ms_autoplot_each).grid(row=2, column=0, columnspan=3, sticky="w")
        self.ms_plot_combined = tk.BooleanVar(value=True)
        ttk.Checkbutton(grid, text="Plot combined at end", variable=self.ms_plot_combined).grid(row=2, column=3, columnspan=3, sticky="w")

        ttk.Label(grid, text="Test N:").grid(row=2, column=6, sticky="e")
        self.ms_test_n = tk.StringVar(value="9")
        ttk.Entry(grid, textvariable=self.ms_test_n, width=6).grid(row=2, column=7, sticky="w")
        ttk.Button(grid, text="Test Matrix xN", command=self._test_matrix_indent_xn_bg).grid(row=2, column=8, padx=6, pady=6)

        ttk.Label(grid, text="Indents/site:").grid(row=2, column=9, sticky="e")
        self.ms_n_per_site = tk.StringVar(value="1")
        ttk.Entry(grid, textvariable=self.ms_n_per_site, width=6).grid(row=2, column=10, sticky="w")

        ttk.Button(grid, text="Run Matrix Scan", command=self._run_matrix_scan_bg).grid(row=2, column=11, padx=6, pady=6)
        ttk.Button(grid, text="Stop", command=lambda:self._run_stop.set()).grid(row=2, column=12, padx=6, pady=6)

    def _build_status(self, root):
        root.columnconfigure(0, weight=1); root.rowconfigure(0, weight=1)
        self.txt = tk.Text(root, wrap="none", font=("TkFixedFont",10), height=20)
        self.txt.config(state="disabled")
        y = ttk.Scrollbar(root, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=y.set)
        self.txt.grid(row=0,column=0,sticky="nsew",padx=6,pady=6)
        y.grid(row=0,column=1,sticky="ns",padx=(0,6),pady=6)

    def _build_data(self, root):
        ttk.Label(root, text="Plots show RAW device data.").grid(row=0,column=0,sticky="w",padx=8,pady=8)
        ttk.Label(root, text=f"Force: {FORCE_FILE}    Motor: {MOTOR_FILE}", foreground="#666").grid(row=1,column=0,sticky="w",padx=8,pady=(0,8))

    # -------- helpers
    def _bg(self, target, *a, **k):
        def wrapper():
            try:
                target(*a, **k)
            except Exception as e:
                self._log("BG error: " + str(e))
                self._log(traceback.format_exc())
        t = threading.Thread(target=wrapper, daemon=True); t.start(); return t

    def _log(self, line: str): self._logbuf.append(line)

    def _pump(self):
        if self._logbuf:
            self.txt.config(state="normal")
            for _ in range(min(150, len(self._logbuf))):
                self.txt.insert("end", self._logbuf.popleft()+"\n")
            self.txt.see("end")
            self.txt.config(state="disabled")
        self.after(80, self._pump)

    def _pump_plots(self):
        try:
            while self._plot_requests:
                fn = self._plot_requests.popleft()
                try: fn()
                except Exception as e:
                    self._log("Plot error: " + str(e))
        finally:
            self.after(120, self._pump_plots)

    # -------- robust feed loader
    def _safe_load_feed(self, path, kind, synth_dt=0.001):
     
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            self._log(f"{kind}: file missing or empty: {path}")
            return None

        try:
            arr = np.genfromtxt(path, comments="#", invalid_raise=False)
        except Exception as e:
            self._log(f"{kind}: read error: {e}")
            return None

        if arr is None:
            self._log(f"{kind}: no data parsed from {path}")
            return None

        arr = np.atleast_2d(arr)
        if arr.size == 0:
            self._log(f"{kind}: parsed array is empty")
            return None

        # If we only have 1 col (e.g., counts only), synthesize time
        if arr.shape[1] == 1:
            y = arr[:, 0].astype(float)
            t = np.arange(y.shape[0], dtype=float) * float(synth_dt)
            arr = np.column_stack([t, y])

        if arr.shape[1] < 2:
            self._log(f"{kind}: still fewer than 2 columns after normalization.")
            return None

        # Drop rows with NaNs in first two columns
        m = np.isfinite(arr[:, 0]) & np.isfinite(arr[:, 1])
        if not np.any(m):
            self._log(f"{kind}: no finite rows in required columns.")
            return None

        return arr[m]

    # -------- simple Z wait
    def _approx_wait_z(self, steps: int):
        t = abs(float(steps)) / max(1.0, Z_APPROX_SPEED_STEPS_PER_S) + float(Z_WAIT_EXTRA_S)
        time.sleep(t)

    # -------- Z actions
    def _connect_motor(self):
        uri = self.uri_var.get().strip()
        if uri.startswith("<"):
            messagebox.showinfo("URI","Enter your XIMC URI, e.g. xi-com:///dev/ttyACM0")
            return
        self.motor_cmdq.put(("connect", uri))

    def _z_move_rel(self, steps: int):
        """Queue a relative Z move. Use 'jog' only (works with your MotorWorker)."""
        try:
            self.motor_cmdq.put(("jog", int(steps)))
            self._log(f"Z cmd: (jog, {int(steps)})")
            return True
        except Exception as e:
            self._log(f"Z move failed: {e}")
            return False


    def _jog(self, direction: str):
        """direction = 'down' or 'up'. Positive steps = DOWN."""
        try:
            mag = abs(int(self.jog_var.get()))
        except Exception:
            messagebox.showerror("Jog","Jog steps must be an integer.")
            return
        steps = +mag if direction == "down" else -mag
        self._z_move_rel(steps)

    def _set_speed(self):
        """Set motor speed only; never touch approach/retract fields."""
        try:
            spd = int(self.speed_var.get())
        except Exception:
            messagebox.showerror("Speed", "Speed must be an integer.")
            return

        # Snapshot approach/retract so we can restore them if anything odd happens
        try:
            self._last_approach = int(self.si_approach.get())
        except Exception:
            self._last_approach = None
        try:
            self._last_retract = int(self.si_retract.get())
        except Exception:
            self._last_retract = None

        # Send ONLY the speed command to the motor worker
        self.motor_cmdq.put(("speed", spd))
        self._log(f"Z speed set to {spd}")

        # Restore approach/retract if they mysteriously changed
        if self._last_approach is not None and self.si_approach.get() != str(self._last_approach):
            self.si_approach.set(str(self._last_approach))
        if self._last_retract is not None and self.si_retract.get() != str(self._last_retract):
            self.si_retract.set(str(self._last_retract))

    # -------- Stage helpers
    def _xy_with_guard(self, action_callable):
        def work():
            if not self.stage.configured():
                self._log("Stage: endpoint not set (use --kim http://IP:5005)")
                self.after(0, lambda: self._set_stage_light("bad")); return
            ok, info = self.stage.info()
            self.after(0, lambda: self._set_stage_light('ok' if ok else 'bad'))
            if not ok:
                self._log(f"Stage not reachable: {info}"); return
            if not self._stage_enabled_once:
                okE, mE = self.stage.enable()
                self._log("Stage auto-enable: " + ("OK" if okE else f"FAIL: {mE}"))
                self._stage_enabled_once = okE
                if not okE: return
            try: action_callable()
            except Exception as e:
                self._log("XY action error: " + str(e))
                self._log(traceback.format_exc())
        self._bg(work)

    def _stage_enable(self):
        def work():
            if not self.stage.configured():
                self._log("Stage: endpoint not set."); self.after(0,lambda:self._set_stage_light("bad")); return
            ok, msg = self.stage.enable()
            self._stage_enabled_once = ok
            self._log("Stage: enabled" if ok else f"Stage enable: {msg}")
            self.after(0,lambda:self._set_stage_light("ok" if ok else "bad"))
        self._bg(work)

    def _stage_set_home(self):
        def work():
            ok1, m1 = self.stage.zero(1); ok2, m2 = self.stage.zero(2)
            self._log("Set Home: zeroed X & Y" if (ok1 and ok2) else f"Set Home failed: {m1} / {m2}")
        self._bg(work)

    def _stage_go_home(self):
        def work():
            okx, mx = self.stage.move_steps(ch=1, steps=0)
            oky, my = self.stage.move_steps(ch=2, steps=0) if okx else (False, mx)
            self._log("Go Home: moved to (0,0)" if (okx and oky) else f"Go Home failed: {mx} / {my}")
        self._bg(work)

    def _stage_nudge_delta(self, ch, delta):
        okp, p = self.stage.position(ch)
        if not okp:
            self._log(f"Nudge ch{ch}: position read failed: {p}"); return
        cur = int(p.get("pos", 0)); tgt = cur + int(delta)
        ok, msg = self.stage.move_steps(ch=ch, steps=tgt)
        self._log(f"Nudge ch{ch}: {cur} -> {tgt} {'OK' if ok else msg}")

    def _stage_move_x(self):
        x = int(self.x_target.get().strip())
        ok, msg = self.stage.move_steps(ch=1, steps=x)
        self._log(f"Move X→{x}: OK" if ok else f"Move X→{x}: {msg}")

    def _stage_move_y(self):
        y = int(self.y_target.get().strip())
        ok, msg = self.stage.move_steps(ch=2, steps=y)
        self._log(f"Move Y→{y}: OK" if ok else f"Move Y→{y}: {msg}")

    def _stage_move_xy(self):
        x = int(self.x_target.get().strip()); y = int(self.y_target.get().strip())
        ok, msg = self.stage.move_xy_steps(x, y)
        self._log(f"Move XY→({x},{y}): OK" if ok else f"Move XY→({x},{y}): {msg}")

    def _stage_move_xy_abs(self, x_abs, y_abs):
        if hasattr(self.stage, "move_xy_steps"):
            return self.stage.move_xy_steps(x_abs, y_abs)
        ok1, m1 = self.stage.move_steps(ch=1, steps=x_abs)
        ok2, m2 = self.stage.move_steps(ch=2, steps=y_abs) if ok1 else (False, m1)
        return (ok1 and ok2), (m1 if not ok1 else m2)
    def _stage_move_xy_abs_retry(self, x_abs, y_abs, retries=2, wait_s=0.4):
        """
        Move to absolute (x_abs, y_abs) with simple retries to ride over
        transient HTTP timeouts from the KIM bridge.
        """
        for attempt in range(retries + 1):
            ok, msg = self._stage_move_xy_abs(x_abs, y_abs)
            if ok:
                return True, "OK"
            self._log(f"Stage move retry {attempt+1}/{retries}: {msg}")
            time.sleep(wait_s)
        return False, msg

        # -------- Indentation primitive (robust)
    def _do_single_indent_steps(self, approach:int, hold_ms:int, retract:int, stop_event:threading.Event=None):
        """Blocking sequence: start F → Z down → hold → stop F → Z up.
           Positive steps = DOWN. Uses MotorWorker 'jog' verb.
           NOTE: Force logging is OFF during retract so only the approach/hold are stored.
        """
        if approach == 0 or retract == 0:
            self._log("Indent: approach/retract cannot be zero — aborting.")
            return
        self._log(f"Indent: approach {approach} steps, hold {hold_ms} ms, retract {retract} steps")

        # Ensure a sane Z speed
        try:
            spd = int(self.speed_var.get())
            if spd > 0:
                self.motor_cmdq.put(("speed", spd))
                self._log(f"Indent: Z speed = {spd}")
            else:
                self._log("Indent: WARNING — Z speed <= 0; set a positive speed in the UI.")
        except Exception:
            pass

        # 1) start force capture  (→ approach+hold will be recorded)
        self.force_cmdq.put("start")
        time.sleep(0.01)

        # 2) approach (DOWN)
        self._log("Indent: DOWN…")
        if not self._z_move_rel(+abs(approach)):
            self._log("Indent: approach move failed."); return
        self._approx_wait_z(approach)


        # 3) hold
        t0 = time.time()
        while (time.time() - t0) * 1000.0 < hold_ms:
            if stop_event is not None and stop_event.is_set():
                self._log("Indent: stop requested during hold → retracting early.")
                break
            time.sleep(0.01)

        # *** IMPORTANT: stop force logging BEFORE retract so retract isn't stored ***
        self.force_cmdq.put("stop")
        time.sleep(0.02)   # small grace to let writer flush

        # 4) retract (UP)  (not recorded)
        self._log("Indent: UP… (force logging OFF)")
        if not self._z_move_rel(-abs(retract)):
            self._log("Indent: retract move failed."); return
        self._approx_wait_z(retract)

        self._log("Indent: done (only approach+hold recorded).")

        # Export and auto-plot full curve
        try:
          
            self._export_force_vs_disp_full_precontact(self._next_export_path("indent_full"))
                # and plot the full curve
            self._plot_requests.append(self._plot_force_disp_full_mainthread)
        except Exception as e:
            self._log(f"Export exception: {e}")

    def _find_contact_idx_robust(self, y: np.ndarray) -> int:
        """
        Estimate the first 'contact' index in y using a noise-aware rule.
        Returns an index >= 1 when contact is detected, else 0.
        """
        n = y.size
        if n < 8:
            return 0

        
        n0 = max(30, min(200, n // 10))
        base = float(np.median(y[:n0]))
        noise = float(np.median(np.abs(y[:n0] - base)) * 1.4826) + 1e-12  # robust σ

        # 1) amplitude criterion: kσ above baseline
        k_sigma = 6.0  # tighten/loosen if needed
        thr = base + k_sigma * noise

        # 2) slope criterion
        w = 7
        dy = np.convolve(np.diff(y, prepend=y[0]), np.ones(w)/w, mode="same")

        # slope threshold
        k_slope = 2.5
        thr_slope = k_slope * noise

        # scan from the end of the baseline window
        for i in range(n0, n):
            if (y[i] > thr) or (dy[i] > thr_slope):
                return i

        # Fallback: 10% of total span above baseline
        span = float(np.max(y) - base)
        if span > 10 * noise:
            fallback_thr = base + 0.10 * span
            j = int(np.argmax(y >= fallback_thr))
            return j if j > 0 else 0

        return 0

    # Single indent button
    def _run_single_indent_bg(self):
        try:
            approach = int(self.si_approach.get().strip())
            hold_ms  = max(0, int(self.si_hold_ms.get().strip()))
            retract  = int(self.si_retract.get().strip())
        except Exception:
            messagebox.showerror("Single Indentation", "Approach/hold/retract must be integers.")
            return
        def run():
            self._do_single_indent_steps(approach, hold_ms, retract)
            if self.si_autoplot.get():
                self._request_plot_force_disp()
        self._bg(run)

    # ---- Test matrix: do N indents in place 
    def _test_matrix_indent_xn_bg(self):
        try:
            n   = max(1, int(self.ms_test_n.get().strip()))
            if self.ms_use_custom_z.get():
                approach = int(self.ms_appr.get().strip())
                hold_ms  = max(0, int(self.ms_hold.get().strip()))
                retract  = int(self.ms_retr.get().strip())
            else:
                approach = int(self.si_approach.get().strip())
                hold_ms  = max(0, int(self.si_hold_ms.get().strip()))
                retract  = int(self.si_retract.get().strip())
        except Exception:
            messagebox.showerror("Test xN", "Enter valid integers for N and Z params.")
            return

        def run():
            self._run_stop.clear()
            self._log(f"Test xN: running {n} consecutive indents in place...")
            for k in range(n):
                if self._run_stop.is_set(): break
                self._log(f"Test indent {k+1}/{n}")
                self._do_single_indent_steps(approach, hold_ms, retract, stop_event=self._run_stop)
                # Save a CSV for each indent
                stem = f"testxn_rep{k+1}"
                self._export_force_vs_disp(self._next_export_path(stem))
            self._log("Test xN: done.")
        self._bg(run)

    # -------- Matrix Scan
    def _run_matrix_scan_bg(self):
        try:
            x0 = int(self.ms_x0.get().strip())
            y0 = int(self.ms_y0.get().strip())
            dx = int(self.ms_dx.get().strip())
            dy = int(self.ms_dy.get().strip())
            nx = int(self.ms_nx.get().strip())
            ny = int(self.ms_ny.get().strip())
            settle_ms = int(self.ms_settle.get().strip())

            if self.ms_use_custom_z.get():
                approach = int(self.ms_appr.get().strip())
                hold_ms  = int(self.ms_hold.get().strip())
                retract  = int(self.ms_retr.get().strip())
            else:
                approach = int(self.si_approach.get().strip())
                hold_ms  = int(self.si_hold_ms.get().strip())
                retract  = int(self.si_retract.get().strip())

            n_per_site = max(1, int(self.ms_n_per_site.get().strip()))
            autoplot_each = self.ms_autoplot_each.get()
            combined_end  = self.ms_plot_combined.get()
        except Exception as e:
            messagebox.showerror("Matrix Scan", f"Invalid parameter: {e}")
            return

        if approach == 0 or retract == 0:
            messagebox.showerror("Matrix Scan", "Approach and Retract must be non-zero.")
            return

        self._run_stop.clear()
    def _apply_force_ceiling(self, disp_um, force_y, y_label, max_mN):
       
        if disp_um is None or force_y is None or disp_um.size == 0 or force_y.size == 0:
            return disp_um, force_y
        if ("mN" not in (y_label or "")) or (max_mN is None):
            return disp_um, force_y

        # find first exceedance from the left
        over = np.nonzero(force_y > float(max_mN))[0]
        if over.size == 0:
            return disp_um, force_y  # never crossed — keep all
        cut = int(over[0])           # first index where it exceeds
        if cut <= 0:
            return disp_um[:0], force_y[:0]  # exceeded immediately
        self._log(f"Plot ceiling: clipped at {max_mN:.3f} mN (N={cut} points kept).")
        return disp_um[:cut], force_y[:cut]

        def run():
            # Stage ready?
            if not self.stage.configured():
                self._log("Matrix: stage endpoint not set.")
                return
            okE, msgE = self.stage.enable()
            if not okE:
                self._log(f"Matrix: stage enable failed: {msgE}")
                return
            self._stage_enabled_once = True

            # Move to start
            # Move to start (use safe wrapper and check)
            self._log(f"Matrix: moving to start position ({x0}, {y0})")
            ok_start, msg_start = self._stage_move_xy_abs_retry(x0, y0, retries=3, wait_s=0.7)

            if not ok_start:
                self._log(f"Matrix: start move failed: {msg_start}")
                return
            time.sleep(max(0, settle_ms) / 1000.0)

            total = nx * ny
            count = 0
            traces = []

            # Row-major scan
            for row in range(ny):
                if self._run_stop.is_set(): break
                for col in range(nx):
                    if self._run_stop.is_set(): break

                    target_x = x0 + col * dx
                    target_y = y0 + row * dy
                    self._log(f"[{count+1}/{total}] Moving to ({target_x},{target_y})")

                    ok_xy, msg_xy = self._stage_move_xy_abs_retry(target_x, target_y, retries=2, wait_s=0.5)

                    if not ok_xy:
                        self._log(f"Matrix: move failed to ({target_x},{target_y}): {msg_xy}")
                        return
                    time.sleep(max(0, settle_ms) / 1000.0)

                    if self._run_stop.is_set(): break

                    # N indents per site
                    for rep in range(n_per_site):
                        if self._run_stop.is_set(): break
                        self._log(f"   → Indent {rep+1}/{n_per_site} at site ({col+1},{row+1})")
                        self._do_single_indent_steps(approach, hold_ms, retract, stop_event=self._run_stop)

                        # For combined trace later: 
                        if combined_end:
                            res = self._force_disp_approach(zero_force=False) 
                            if res is not None:
                                z_um, y = res[0], res[1]
                                traces.append((z_um, y))

                        if autoplot_each:
                            self._request_plot_force_disp()

                    count += 1

            self._log(f"Matrix: finished {count}/{total} sites.")
            if self._run_stop.is_set():
                self._log("Matrix: stopped by user.")

            # Combined plot at end
            if traces and self.ms_plot_combined.get():
                def _plot_all():
                    plt.figure("Force vs Displacement — Combined (approach only)")
                    for (z_um, y) in traces:
                        plt.plot(z_um, y, linewidth=1.0)
                    plt.xlabel("Z displacement (µm)")
                    plt.ylabel("Force")
                    plt.title(f"Force vs Displacement — Combined ({len(traces)} traces)")
                    plt.grid(True, alpha=0.3); plt.tight_layout(); plt.show(block=False)
                self._plot_requests.append(_plot_all)

        self._bg(run)
    def _force_disp_simple(self, offset_um: float = SIMPLE_DISP_OFFSET_UM):
        
        F = self._safe_load_feed(FORCE_FILE, "FORCE")
        M = self._safe_load_feed(MOTOR_FILE, "MOTOR")
        if F is None or M is None:
            self._log("Simple F–Disp: missing/invalid feeds.")
            return None

        # Force channel
        tF = F[:, 0].astype(float)
        if F.shape[1] >= 4:
            y = F[:, 3].astype(float); y_label = "Force (mN)"
        else:
            y = F[:, 1].astype(float); y_label = "Force (ADC counts)"
        sF = np.argsort(tF); tF = tF[sF]; y = y[sF]

        # Motor displacement (mm)
        tM = M[:, 0].astype(float); dM_mm = M[:, 1].astype(float)
        if tM.size < 2 or tF.size < 1:
            self._log("Simple F–Disp: data too short.")
            return None

        # Overlap
        t_lo = max(tF.min(), tM.min()); t_hi = min(tF.max(), tM.max())
        if not (t_hi > t_lo):
            self._log("Simple F–Disp: no overlap between windows.")
            return None
        mF = (tF >= t_lo) & (tF <= t_hi); mM = (tM >= t_lo) & (tM <= t_hi)
        if not (np.any(mF) and np.any(mM)):
            self._log("Simple F–Disp: empty overlap.")
            return None
        tF_ov = tF[mF]; y_ov = y[mF]
        tM_ov = tM[mM]; dM_ov = dM_mm[mM]

        # Interp displacement (µm)
        disp_um = np.interp(tF_ov, tM_ov, dM_ov).astype(float) * 1e3

        # Optional constant offset so left side can go negative
        if offset_um != 0.0:
            disp_um = disp_um - float(offset_um)

        return disp_um, y_ov, y_label

    def _plot_force_disp_simple_mainthread(self, offset_um: float = SIMPLE_DISP_OFFSET_UM):
        res = self._force_disp_simple(offset_um=offset_um)
        if not res: return
        x_um, y, y_label = res
        x_um, y = self._apply_force_ceiling(x_um, y, y_label, MAX_FORCE_PLOT_MN)
        if x_um.size == 0:
            self._log("Plot ceiling: nothing to plot (all > ceiling).")
            return

        plt.figure("Force vs Displacement (SIMPLE)")
        plt.plot(x_um, y, linewidth=1.0, label="data")

        # Optional: extrapolate a short left segment for visual context (dotted)
        if EXTRAPOLATE_LEFT_UM > 0 and x_um.size > 5:
            nfit = min(EXTRAPOLATE_FIT_SAMPLES, x_um.size)
            xf = x_um[:nfit]; yf = y[:nfit]
            try:
                # simple linear LSQ fit on the earliest samples
                A = np.vstack([xf, np.ones_like(xf)]).T
                slope, intercept = np.linalg.lstsq(A, yf, rcond=None)[0]
                x_left = np.linspace(x_um.min() - EXTRAPOLATE_LEFT_UM, x_um.min(), 30)
                y_left = slope * x_left + intercept
                plt.plot(x_left, y_left, linestyle="--", linewidth=1.0, label="extrapolation")
            except Exception as e:
                self._log(f"Extrapolation skipped: {e}")

        plt.xlabel("Displacement (µm)")
        plt.ylabel(y_label)
        plt.title("Force vs Displacement — Simple (no contact ops)")
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.tight_layout()
        plt.pause(0.001)

    def _next_export_path(self, stem: str):
        _ensure_dir(EXPORT_DIR)
        ts = time.strftime("%Y%m%d-%H%M%S")
        return os.path.join(EXPORT_DIR, f"{stem}_{ts}.csv")

    def _export_force_vs_disp_full_precontact(self, out_path: str):
        """
        Save FULL curve with pre-contact (negative displacement allowed).
        Columns: disp_um, force_mN (or force_counts)
        """
        res = self._force_disp_full(start_threshold=None, allow_negative=True)
        if not res:
            self._log("Export (full): cannot build force/disp arrays.")
            return False
        disp_um, force_y, y_label = res
        y_name = "force_mN" if "mN" in y_label else "force_counts"
        _ensure_dir(os.path.dirname(out_path) or ".")
        header = f"disp_um,{y_name}"
        data = np.column_stack([disp_um, force_y])
        try:
            np.savetxt(out_path, data, delimiter=",", header=header, comments="", fmt="%.6f")
            self._log(f"Export (full): saved {out_path} ({data.shape[0]} rows)")
            return True
        except Exception as e:
            self._log(f"Export (full) error: {e}")
            return False


    # -------- Streaming UI (MQTT publisher launcher)
    def _build_streaming(self, root):
        pad = {"padx":8, "pady":6}
        root.columnconfigure(1, weight=1)

        frm = ttk.LabelFrame(root, text="MQTT Streaming")
        frm.grid(row=0, column=0, sticky="ew", **pad)
        for c in range(6):
            frm.columnconfigure(c, weight=(1 if c in (1,3,5) else 0))

        # Small status light
        ttk.Label(frm, text="Publisher:").grid(row=0, column=0, sticky="e")
        self.pub_light = tk.Canvas(frm, width=14, height=14, highlightthickness=0)
        self.pub_light.grid(row=0, column=1, sticky="w")
        self._set_pub_light("off")

        # Broker/Topic controls (defaults match mqtt_publisher.py)
        ttk.Label(frm, text="Host:").grid(row=1, column=0, sticky="e")
        self.mq_host = tk.StringVar(value=os.getenv("MQTT_HOST", "localhost"))
        ttk.Entry(frm, textvariable=self.mq_host, width=18).grid(row=1, column=1, sticky="w")

        ttk.Label(frm, text="Port:").grid(row=1, column=2, sticky="e")
        self.mq_port = tk.StringVar(value=os.getenv("MQTT_PORT", "1883"))
        ttk.Entry(frm, textvariable=self.mq_port, width=8).grid(row=1, column=3, sticky="w")

        ttk.Label(frm, text="Topic:").grid(row=1, column=4, sticky="e")
        self.mq_topic = tk.StringVar(value=os.getenv("MQTT_TOPIC", "MON"))
        ttk.Entry(frm, textvariable=self.mq_topic, width=12).grid(row=1, column=5, sticky="w")

        ttk.Label(frm, text="Rate (Hz):").grid(row=2, column=0, sticky="e")
        self.mq_hz = tk.StringVar(value=os.getenv("PUBLISH_HZ", "100"))
        ttk.Entry(frm, textvariable=self.mq_hz, width=8).grid(row=2, column=1, sticky="w")

        ttk.Label(frm, text="Device ID:").grid(row=2, column=2, sticky="e")
        self.mq_devid = tk.StringVar(value=os.getenv("DEVICE_ID", "HqSTf2PYpg6t"))
        ttk.Entry(frm, textvariable=self.mq_devid, width=18).grid(row=2, column=3, sticky="w")

        ttk.Label(frm, text="Device Token:").grid(row=2, column=4, sticky="e")
        self.mq_devtok = tk.StringVar(value=os.getenv("DEVICE_TOKEN", "av40HTAb0O5VGQ0D"))
        ttk.Entry(frm, textvariable=self.mq_devtok, width=18).grid(row=2, column=5, sticky="w")

        # Start/Stop buttons
        btns = ttk.Frame(frm); btns.grid(row=3, column=0, columnspan=6, sticky="w", pady=(6,0))
        ttk.Button(btns, text="Start Publisher", command=self._publisher_start).grid(row=0, column=0, padx=6)
        ttk.Button(btns, text="Stop Publisher",  command=self._publisher_stop ).grid(row=0, column=1, padx=6)

        # Info
        ttk.Label(root, text="Streams latest Force and Displacement at the chosen rate. "
                             "Uses mqtt_publisher.py as a child process.",
                  foreground="#666").grid(row=1, column=0, sticky="w", **pad)

    # -------- Camera tab (USB microscope via OpenCV)
    def _build_camera(self, root):
        pad = {"padx":8, "pady":6}
        root.columnconfigure(0, weight=1)

        frm = ttk.LabelFrame(root, text="USB Camera")
        frm.grid(row=0, column=0, sticky="ew", **pad)
        for c in range(8):
            frm.columnconfigure(c, weight=(1 if c in (1,3,5,7) else 0))

        ttk.Label(frm, text="Device index:").grid(row=0, column=0, sticky="e")
        self.cam_index = tk.StringVar(value="0")
        ttk.Entry(frm, textvariable=self.cam_index, width=6).grid(row=0, column=1, sticky="w")

        ttk.Label(frm, text="Width:").grid(row=0, column=2, sticky="e")
        self.cam_w = tk.StringVar(value="1280")
        ttk.Entry(frm, textvariable=self.cam_w, width=8).grid(row=0, column=3, sticky="w")

        ttk.Label(frm, text="Height:").grid(row=0, column=4, sticky="e")
        self.cam_h = tk.StringVar(value="720")
        ttk.Entry(frm, textvariable=self.cam_h, width=8).grid(row=0, column=5, sticky="w")

        ttk.Button(frm, text="Start", command=self._camera_start).grid(row=0, column=6, padx=6)
        ttk.Button(frm, text="Stop",  command=self._camera_stop ).grid(row=0, column=7, padx=6)

        self.cam_light = tk.Canvas(frm, width=14, height=14, highlightthickness=0)
        self.cam_light.grid(row=0, column=8, sticky="w")
        self._set_cam_light("off")

        view = ttk.LabelFrame(root, text="Live View")
        view.grid(row=1, column=0, sticky="nsew", **pad)
        root.rowconfigure(1, weight=1)
        view.columnconfigure(0, weight=1)
        view.rowconfigure(0, weight=1)

        self.cam_label = tk.Label(view, bg="#000")
        self.cam_label.grid(row=0, column=0, sticky="nsew")

        if not _CV2_OK:
            ttk.Label(root, text="OpenCV missing — install on Raspberry Pi with: "
                                 "sudo apt install python3-opencv",
                      foreground="#a00").grid(row=2, column=0, sticky="w", **pad)

    def _set_cam_light(self, state):
        self.cam_light.delete("all")
        color = {"on":"#11c000", "off":"#bbbbbb", "err":"#cc0000"}.get(state,"#bbbbbb")
        self.cam_light.create_oval(2,2,12,12, fill=color, outline=color)

    def _camera_start(self):
        if not _CV2_OK:
            messagebox.showerror("Camera", "OpenCV (cv2) is not installed.")
            return
        if self._camera_running:
            self._log("Camera already running.")
            return

        try:
            idx = int(self.cam_index.get().strip())
            w   = int(self.cam_w.get().strip())
            h   = int(self.cam_h.get().strip())
        except Exception:
            messagebox.showerror("Camera", "Index/Width/Height must be integers.")
            return

        self._log(f"Attempting to open camera index {idx} ...")
        self._set_cam_light("off")

        # Run camera open in background thread so GUI doesn’t freeze
        def open_cam():
            import time
            cap = None
            t0 = time.time()
            while time.time() - t0 < 2.0:  # try for up to 2 seconds
                cap = cv2.VideoCapture(idx, cv2.CAP_ANY)
                if cap and cap.isOpened():
                    break
                time.sleep(0.1)

            if not cap or not cap.isOpened():
                self._log(f"Camera index {idx} failed to open.")
                self.after(0, lambda: (
                    self._set_cam_light("err"),
                    messagebox.showerror("Camera", f"Cannot open camera index {idx}")
                ))
                return

            # Configure resolution and FPS
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            cap.set(cv2.CAP_PROP_FPS, 30)

            self._camera_cap = cap
            self._camera_running = True
            self.after(0, lambda: (
                self._set_cam_light("on"),
                self._log(f"Camera started (index={idx}, {w}x{h})"),
                self._camera_update()
            ))

        self._bg(open_cam)

    def _camera_update(self):
        if not self._camera_running or self._camera_cap is None:
            return
        ok, frame = self._camera_cap.read()
        if ok:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            imgtk = ImageTk.PhotoImage(image=img)
            self._cam_imgtk = imgtk
            self.cam_label.configure(image=imgtk)
        else:
            self._log("Camera frame read failed.")
        self._cam_job = self.after(33, self._camera_update)

    def _camera_stop(self):
        if self._cam_job is not None:
            try: self.after_cancel(self._cam_job)
            except Exception: pass
            self._cam_job = None
        if self._camera_cap is not None:
            try: self._camera_cap.release()
            except Exception: pass
        self._camera_cap = None
        self._camera_running = False
        self._set_cam_light("off")
        self._cam_imgtk = None
        try: self.cam_label.configure(image="", text="")
        except Exception: pass
        self._log("Camera stopped.")

    def _set_pub_light(self, state: str):
        self.pub_light.delete("all")
        color = {"on":"#11c000", "off":"#bbbbbb", "err":"#cc0000"}.get(state, "#bbbbbb")
        self.pub_light.create_oval(2,2,12,12, fill=color, outline=color)

    def _publisher_start(self):
        if self._publisher_proc and (self._publisher_proc.poll() is None):
            self._log("Publisher already running.")
            return

        # Path to the publisher script
        script_path = os.path.join(os.path.dirname(__file__), "mqtt_publisher.py")
        if not os.path.exists(script_path):
            messagebox.showerror("MQTT", f"Cannot find mqtt_publisher.py at {script_path}")
            return

        # Build env for the child process (so it uses the same files/rate/topic)
        env = os.environ.copy()
        env["MQTT_HOST"]  = self.mq_host.get().strip()
        env["MQTT_PORT"]  = self.mq_port.get().strip()
        env["MQTT_TOPIC"] = self.mq_topic.get().strip()

        env["PUBLISH_HZ"] = self.mq_hz.get().strip()
        env["DEVICE_ID"]  = self.mq_devid.get().strip()
        env["DEVICE_TOKEN"] = self.mq_devtok.get().strip()

        # Make sure feeds line up with your GUI constants
        env["MOTOR_FEED"] = MOTOR_FILE
        env["FORCE_FEED"] = FORCE_FILE

        # Launch child; capture stdout/stderr so we can surface logs
        try:
            self._publisher_proc = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env
            )
        except Exception as e:
            self._log(f"Publisher start failed: {e}")
            self._set_pub_light("err")
            return

        self._set_pub_light("on")
        self._log("Publisher started.")

        # Background reader to pipe child logs into Status tab
        def _readout():
            try:
                for line in self._publisher_proc.stdout:
                    self._log("[PUB] " + line.rstrip())
            except Exception as e:
                self._log(f"[PUB] stdout reader error: {e}")
            finally:
                # When process ends, update light
                self._set_pub_light("off")
        self._publisher_reader = threading.Thread(target=_readout, daemon=True)
        self._publisher_reader.start()

    def _publisher_stop(self):
        if not self._publisher_proc:
            return
        if self._publisher_proc.poll() is None:
            try:
                # Be gentle first
                self._publisher_proc.send_signal(signal.SIGINT)
                try:
                    self._publisher_proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self._publisher_proc.terminate()
            except Exception:
                pass
        self._publisher_proc = None
        self._set_pub_light("off")
        self._log("Publisher stopped.")

            # -------- Full force–displacement (no trimming)
    def _force_disp_full(self, start_threshold=None, allow_negative=False):
        """
        Build FORCE vs DISP (µm) over the full overlap window.
        If allow_negative=True, displacement is zeroed at contact but NOT clamped,
        so pre-contact appears as negative displacement.
        """
        F = self._safe_load_feed(FORCE_FILE, "FORCE")
        M = self._safe_load_feed(MOTOR_FILE, "MOTOR")
        if F is None or M is None:
            self._log("Force/Disp (full): missing/invalid feeds.")
            return None

        # Choose force channel
        tF = F[:, 0].astype(float)
        if F.shape[1] >= 4:
            y = F[:, 3].astype(float); y_label = "Force (mN)"
        else:
            y = F[:, 1].astype(float); y_label = "Force (ADC counts)"
        sF = np.argsort(tF); tF = tF[sF]; y = y[sF]

        # Motor: (time, disp_mm)
        tM = M[:, 0].astype(float); dM_mm = M[:, 1].astype(float)
        if tM.size < 2 or tF.size < 1:
            self._log("Force/Disp (full): data too short.")
            return None

        # Overlap
        t_lo = max(tF.min(), tM.min()); t_hi = min(tF.max(), tM.max())
        if not (t_hi > t_lo):
            self._log("Force/Disp (full): no overlap between windows.")
            return None
        mF = (tF >= t_lo) & (tF <= t_hi)
        mM = (tM >= t_lo) & (tM <= t_hi)
        if not (np.any(mF) and np.any(mM)):
            self._log("Force/Disp (full): empty overlap.")
            return None

        tF_ov = tF[mF]; y_ov = y[mF]
        tM_ov = tM[mM]; dM_ov = dM_mm[mM]

        # Interpolate displacement at FORCE timestamps
        disp_um_ov = np.interp(tF_ov, tM_ov, dM_ov).astype(float) * 1e3

        # Optional early cut by force threshold (skip if we want pre-contact)
        if (start_threshold is not None) and np.any(y_ov >= start_threshold):
            i0 = int(np.argmax(y_ov >= start_threshold))
            i0 = max(0, i0 - 5)
            tF_ov, y_ov, disp_um_ov = tF_ov[i0:], y_ov[i0:], disp_um_ov[i0:]

        # Drop one leading outlier if it looks like a glitch
        n0 = min(50, y_ov.size)
        if n0 > 5:
            med = np.median(y_ov[:n0])
            mad = np.median(np.abs(y_ov[:n0] - med)) + 1e-12
            if y_ov[0] > med + 4*mad:
                y_ov       = y_ov[1:]
                disp_um_ov = disp_um_ov[1:]
                tF_ov      = tF_ov[1:]
        # --- Zero displacement at robust contact; keep negatives if requested ---
        try:
            ci = self._find_contact_idx_robust(y_ov)
            if ci > 0:
                contact_offset = float(disp_um_ov[ci])
                disp_um_ov = disp_um_ov - contact_offset
                if not allow_negative:
                    # Old behavior (clamp). With allow_negative=True we skip this.
                    disp_um_ov = disp_um_ov - np.min(disp_um_ov)
                self._log(f"Contact @ i={ci}, offset {contact_offset:.2f} µm")
            else:
                self._log("Contact not detected robustly; keeping original displacement (no negatives).")
        except Exception as e:
            self._log(f"Contact calc failed: {e}")


        s = np.argsort(disp_um_ov)
        return disp_um_ov[s], y_ov[s], y_label
    def _plot_force_disp_full_mainthread(self):
        res = self._force_disp_full(start_threshold=None, allow_negative=True)
        if not res:
            return
        x_um, y, y_label = res
        # apply 0.40 mN ceiling if available
        x_um, y = self._apply_force_ceiling(x_um, y, y_label, MAX_FORCE_PLOT_MN)
        if x_um.size == 0:
            self._log("Plot ceiling: nothing to plot (all > ceiling).")
            return

        plt.figure("Force vs Displacement (FULL)")
        plt.plot(x_um, y, linewidth=1.0)
        plt.xlabel("Displacement (µm)")
        plt.ylabel(y_label)
        plt.title(f"Force vs Displacement — Full (≤ {MAX_FORCE_PLOT_MN:.2f} mN)")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.pause(0.001)


    # -------- Plot request wrappers
    def _request_plot_force_disp(self):
        self._plot_requests.append(self._plot_force_disp_full_mainthread)

    def _request_plot_counts_steps(self):
        self._plot_requests.append(self._plot_counts_steps_mainthread)

        # -------- Shared force–disp builder (approach-only, zeroed start)
    def _force_disp_approach(self, zero_force: bool = False):
        """
        Build FORCE vs DISP (µm) using raw samples only.
        - No baseline subtraction, no sign flip, no filtering.
        - Motor displacement is linearly interpolated at force timestamps.
        - We only trim by displacement up to the first global max (approach).
        Returns (disp_um, force_y, y_label) or None.
        """
        F = self._safe_load_feed(FORCE_FILE, "FORCE")
        M = self._safe_load_feed(MOTOR_FILE, "MOTOR")
        if F is None or M is None:
            self._log("Force/Disp: missing/invalid feeds.")
            return None

        # Force channel: prefer mN if present, else counts
        tF = F[:, 0].astype(float)
        if F.shape[1] >= 4:
            y = F[:, 3].astype(float); y_label = "Force (mN)"
        else:
            y = F[:, 1].astype(float); y_label = "Force (ADC counts)"

        sF = np.argsort(tF); tF = tF[sF]; y = y[sF]

        # Motor displacement (mm) → interp at force timestamps
        tM = M[:, 0].astype(float); dM_mm = M[:, 1].astype(float)
        if tM.size < 2 or tF.size < 1:
            self._log("Force/Disp: data too short.")
            return None

        t_lo = max(tF.min(), tM.min()); t_hi = min(tF.max(), tM.max())
        if not (t_hi > t_lo):
            self._log("Force/Disp: no overlap between windows.")
            return None

        mF = (tF >= t_lo) & (tF <= t_hi); mM = (tM >= t_lo) & (tM <= t_hi)
        if not (np.any(mF) and np.any(mM)):
            self._log("Force/Disp: empty overlap masks.")
            return None

        tF_ov = tF[mF]; y_ov = y[mF]
        tM_ov = tM[mM]; dM_ov = dM_mm[mM]

        disp_um = np.interp(tF_ov, tM_ov, dM_ov).astype(float) * 1e3

        # Sort by displacement and keep only approach (up to first max)
        s = np.argsort(disp_um)
        disp_um = disp_um[s]
        y_ov    = y_ov[s]

        disp_um, y_ov, _, _ = self._trim_to_approach(disp_um, y_ov)
        if disp_um.size == 0:
            self._log("Force/Disp: nothing after approach trimming.")
            return None

        return disp_um, y_ov, y_label

    # -------- Plotters
    def _plot_force_disp_mainthread(self):
        res = self._force_disp_approach(zero_force=False)
        if not res:
            return
        x_um, y, y_label = res

        plt.figure("Force vs Displacement (approach only)")
        plt.plot(x_um, y, linewidth=1.0)
        plt.xlabel("Displacement (µm)")
        plt.ylabel(y_label)
        plt.title("Force vs Displacement — approach only")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.pause(0.001)

    def _plot_counts_steps_mainthread(self):
        F = self._safe_load_feed(FORCE_FILE, "FORCE")
        M = self._safe_load_feed(MOTOR_FILE, "MOTOR")
        if F is None or M is None:
            messagebox.showerror("Load error", "Missing or invalid force/motor feed data.")
            return

        # Force: time + counts (+ volts optional)
        tF = F[:, 0].astype(float)
        counts = F[:, 1].astype(float)
        volts  = F[:, 2].astype(float) if F.shape[1] >= 3 else None
        sF = np.argsort(tF)
        tF = tF[sF]; counts = counts[sF]; volts = (volts[sF] if volts is not None else None)

        # Motor: time + disp_mm -> steps
        tM = M[:, 0].astype(float); disp_mm = M[:, 1].astype(float)
        steps = (disp_mm / max(STEP_TO_MM, 1e-18)).astype(float)

        if tM.size < 2 or tF.size < 1:
            self._log("Plot: data too short."); return

        # Overlap
        t_lo = max(np.min(tF), np.min(tM))
        t_hi = min(np.max(tF), np.max(tM))
        if not (t_hi > t_lo):
            self._log("Plot: no overlap between force & motor time windows."); return

        maskF = (tF >= t_lo) & (tF <= t_hi)
        maskM = (tM >= t_lo) & (tM <= t_hi)
        tF_ov = tF[maskF]; c_ov = counts[maskF]
        v_ov  = volts[maskF] if volts is not None else None
        tM_ov = tM[maskM]; s_ov = steps[maskM]
        if tM_ov.size < 2 or tF_ov.size < 1:
            self._log("Plot: not enough overlap between force & motor."); return

        # Interpolate steps at the force timestamps (smooth relation)
        steps_at_F = np.interp(tF_ov, tM_ov, s_ov).astype(float)

        # Sort by steps
        s = np.argsort(steps_at_F)
        x_steps = steps_at_F[s]
        y_counts = c_ov[s]
        y_volts = v_ov[s] if v_ov is not None else None

        plt.figure("Counts vs Steps")
        plt.plot(x_steps, y_counts, linewidth=1.0, label="ADC counts")
        if y_volts is not None:
            plt.plot(x_steps, y_volts, linewidth=1.0, label="Volts")
        plt.xlabel("Motor steps")
        plt.ylabel("Signal")
        plt.title("ADC counts vs Motor Steps")
        plt.grid(True, alpha=0.3)
        if y_volts is not None:
            plt.legend()
        plt.tight_layout()
        plt.pause(0.001)

    # -------- Trim to approach
    def _trim_to_approach(self,
                        disp_um: np.ndarray,
                        y: np.ndarray,
                        tF: np.ndarray = None,
                        tM: np.ndarray = None):
     
        if disp_um.size == 0:
            return disp_um, y, tF, tM
        end_i = int(np.argmax(disp_um))
        sl = slice(0, end_i + 1)
        disp_um = disp_um[sl]
        y = y[sl]
        if tF is not None: tF = tF[sl]
        if tM is not None: tM = tM[sl]
        return disp_um, y, tF, tM

    # -------- (legacy) extract current Z–Force pair (kept for compatibility)
    def _extract_current_z_force(self):
        F = self._safe_load_feed(FORCE_FILE, "FORCE")
        M = self._safe_load_feed(MOTOR_FILE, "MOTOR")
        if F is None or M is None:
            return None

        # Force: time + preferred y (mN if available)
        tF = F[:, 0].astype(float)
        if F.shape[1] >= 4:
            yF = F[:, 3].astype(float)         # force mN
        else:
            yF = F[:, 1].astype(float)         # counts fallback
        sF = np.argsort(tF)
        tF = tF[sF]; yF = yF[sF]

        # Motor: time + displacement (mm)
        tM = M[:, 0].astype(float)
        dM = M[:, 1].astype(float)

        if tM.size < 2 or tF.size < 1:
            return None

        t_lo = max(tF.min(), tM.min())
        t_hi = min(tF.max(), tM.max())
        if not (t_hi > t_lo):
            return None

        maskF = (tF >= t_lo) & (tF <= t_hi)
        maskM = (tM >= t_lo) & (tM <= t_hi)
        if not np.any(maskF) or not np.any(maskM):
            return None

        tF_ov = tF[maskF]; yF_ov = yF[maskF]
        tM_ov = tM[maskM]; dM_ov = dM[maskM]
        if tM_ov.size < 2 or tF_ov.size < 1:
            return None

        idx = np.searchsorted(tM_ov, tF_ov, side='right') - 1
        idx[idx < 0] = 0
        idx[idx >= tM_ov.size] = tM_ov.size - 1
        disp_at_F = dM_ov[idx].astype(float)   # mm

        s = np.argsort(disp_at_F)
        return disp_at_F[s], yF_ov[s]

    # -------- shutdown
    def _on_close(self):
        try: self.force_cmdq.put("stop")
        except: pass
        try: self.force_cmdq.put("quit")
        except: pass
        try: self.motor_cmdq.put(("quit", None))
        except: pass
        try: self._publisher_stop()
        except: pass
        try: self._camera_stop()
        except: pass

        self.after(200, self.destroy)

# ---------- entry ----------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", default="", help="XIMC URI (e.g. xi-com:///dev/ttyACM0)")
    ap.add_argument("--kim", default="", help="Stage backend endpoint (e.g. http://192.168.5.3:5005)")
    args = ap.parse_args()
    App(uri=args.uri, kim_endpoint=args.kim).mainloop()
