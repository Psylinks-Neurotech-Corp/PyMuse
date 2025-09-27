import math
import pathlib
import queue
import threading
import time
import sys
import textwrap
from collections import deque
from typing import Deque, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import tkinter as tk
from tkinter import messagebox, ttk

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from muse_py import Muse, MuseConfigurationInfo
except Exception as exc:  # pragma: no cover
    Muse = None
    MuseConfigurationInfo = None
    _import_error = exc
else:
    _import_error = None

EEG_LABELS_BY_COUNT: Dict[int, List[str]] = {
    4: ["TP9", "AF7", "AF8", "TP10"],
    5: ["TP9", "AF7", "AF8", "TP10", "POz"],
    6: ["TP9", "AF7", "AF8", "TP10", "POz", "AUX1"],
}
MODEL_SPECIFIC_EEG: Dict[str, List[str]] = {
    "Muse 2014 (MU-01)": ["TP9", "AF7", "AF8", "TP10"],
    "Muse 2016 (MU-02)": ["TP9", "AF7", "AF8", "TP10", "POz"],
    "Muse 2 (MU-03)": ["TP9", "AF7", "AF8", "TP10"],
    "Muse S 2019 (MU-04)": ["TP9", "AF7", "AF8", "TP10", "POz"],
    "Muse S 2021 (MU-05)": ["TP9", "AF7", "AF8", "TP10", "POz"],
    "Muse 2 2024 (MU-06)": ["TP9", "AF7", "AF8", "TP10", "POz"],
    "Muse S 2025 (MS-03)": ["TP9", "AF7", "AF8", "TP10", "POz", "AUX1"],
}
OPTICS_LABELS = [
    "Optics1", "Optics2", "Optics3", "Optics4",
    "Optics5", "Optics6", "Optics7", "Optics8",
    "Optics9", "Optics10", "Optics11", "Optics12",
    "Optics13", "Optics14", "Optics15", "Optics16",
]
DEFAULT_CHANNEL_LABELS: Dict[str, List[str]] = {
    "ACC": ["X", "Y", "Z"],
    "GYRO": ["X", "Y", "Z"],
    "PPG": ["PPG1", "PPG2", "PPG3"],
    "DRL_REF": ["DRL", "REF"],
    "BATTERY": [
        "% remaining", "millivolts", "temp C", "avg current uA",
        "time to empty s", "time to full s", "capacity mAh",
        "remaining mAh", "age %", "cycles",
    ],
}
PACKET_UNITS: Dict[str, str] = {
    "EEG": "uV",
    "OPTICS": "uA",
    "ACC": "g",
    "GYRO": "deg/s",
    "PPG": "a.u.",
    "BATTERY": "",
    "DRL_REF": "uV",
}

EEG_COLORS = ["#00ff99", "#33cfff", "#ff6b6b", "#ffa94d", "#b197fc", "#12b886"]
OPTICS_COLORS = [
    "#ff922b", "#f783ac", "#94d82d", "#4dabf7",
    "#9775fa", "#ff8787", "#63e6be", "#ffd43b",
    "#a9e34b", "#22b8cf", "#e599f7", "#ffc078",
    "#74c0fc", "#fab005", "#ff4d6d", "#2ec4b6",
]
HISTORY_LENGTHS: Dict[str, int] = {
    "EEG": 512,
    "OPTICS": 512,
    "PPG": 512,
    "ACC": 256,
    "GYRO": 256,
    "BATTERY": 64,
    "DRL_REF": 128,
}

SPECTRUM_MAX_FRAMES = 120
SPECTRUM_DISPLAY_MAX_HZ = 70.0

PRESET_SUMMARIES: Dict[str, str] = {
    "20": "Muse 2016 research preset (5 EEG channels, 12-bit, 256 Hz).",
    "21": "Default EEG streaming (Muse 2 / Muse S): 4 EEG channels @ 256 Hz with motion sensors enabled.",
    "1031": "EEG + optics with low LED intensity (battery friendly).",
    "1032": "EEG + optics with medium LED intensity.",
    "1033": "EEG + optics with high LED intensity.",
    "1034": "EEG + expanded optics developer preset (Muse Athena).",
    "1035": "EEG + optics commonly used on Muse S / Muse S 2025 (four optical pairs).",
    "1036": "EEG + full optics array (up to 16 channels on Muse Athena).",
}

PRESET_HELP_TEXT = textwrap.dedent("""\
Preset overview
---------------
20   - Legacy Muse 2016 research preset (5 EEG channels).
21   - Default EEG streaming for Muse 2 / Muse S (4 EEG channels @ 256 Hz).
1031 - EEG + optics with low LED intensity (conserves battery).
1032 - EEG + optics with medium LED intensity.
1033 - EEG + optics with high LED intensity.
1034 - EEG + expanded optics developer preset (Muse Athena).
1035 - EEG + optics commonly used on Muse S / Muse S 2025 (four optical pairs).
1036 - EEG + full optics array (up to 16 channels on Muse Athena).

Tip: Start with the default for your headset (21 for EEG-only, 1035 for Muse S optics, 1036 for Muse Athena) and
only change if you need different optics power or channel counts.
""")

class MuseApp:
    PACKET_ORDER = ("EEG", "OPTICS", "PPG", "ACC", "GYRO", "BATTERY", "DRL_REF")

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Muse Wrapper Showcase")
        self.root.geometry("1120x690")

        self.muse: Optional[Muse] = None
        self.devices: List = []
        self.connected = False

        self.data_queue: queue.Queue = queue.Queue(maxsize=2048)
        self.event_queue: queue.Queue = queue.Queue()

        self.latest_values: Dict[str, Tuple[int, List[float]]] = {}
        self.sample_windows: Dict[str, Deque[float]] = {
            pkt: deque(maxlen=512) for pkt in self.PACKET_ORDER
        }
        self.channel_buffers: Dict[str, List[Deque[float]]] = {}
        self.config: Optional[MuseConfigurationInfo] = None
        self.connection_state = "DISCONNECTED"
        self.eeg_sample_rate = 256.0
        self.eeg_buffers: List[Deque[float]] = []
        self.eeg_channel_ranges: Dict[str, float] = {}
        self.optics_channel_ranges: Dict[str, float] = {}
        self.spectrum_frames: Deque[np.ndarray] = deque(maxlen=SPECTRUM_MAX_FRAMES)
        self.spectrum_freqs: Optional[np.ndarray] = None
        self._spectrum_window_seconds = 0.0
        self._spectrum_fft_size = 256

        self.eeg_display_range = 200.0
        self.optics_display_range = 12.0

        self.spectrum_status_var: Optional[tk.StringVar] = None
        self._eeg_scale_presets = [1, 5, 10, 20, 50, 100, 150, 200, 300, 500, 1000]
        self._optics_scale_presets = [
            0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.5,
            10.0, 12.0, 15.0, 20.0, 30.0, 40.0, 60.0,
            80.0, 120.0, 200.0, 320.0, 480.0, 640.0, 800.0, 1000.0,
        ]
        self._eeg_scale_combo_values = [self._format_scale_value(v) for v in self._eeg_scale_presets]
        self.detrend_var = tk.BooleanVar(master=self.root, value=True)
        self.eeg_scale_combo: Optional[ttk.Combobox] = None
        self._waveform_job: Optional[str] = None
        self.preset_hint_var: Optional[tk.StringVar] = None
        self._eeg_filter_taps: Optional[np.ndarray] = None
        self._eeg_filter_state: Dict[str, np.ndarray] = {}
        self._lowpass_cutoff = 50.0
        self._lowpass_enabled = True

        self._build_ui()
        self._configure_eeg_lowpass(self.eeg_sample_rate)

        if Muse is None:
            messagebox.showerror(
                "Muse wrapper missing",
                "Couldn't import muse_py. Build it via CMake.\n" + f"Original error: {_import_error!r}"
            )
        else:
            try:
                self.muse = Muse()
            except Exception as exc:
                messagebox.showerror("Muse init failed", str(exc))

        self.root.after(150, self._process_events)
        self._queue_waveform_refresh(250)

    # ---------------------- UI setup ---------------------------
    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        controls = ttk.LabelFrame(main, text="Discovery & Connection")
        controls.pack(fill=tk.X)

        ttk.Button(controls, text="Scan", command=self._scan_devices).grid(row=0, column=0, padx=4, pady=4)
        ttk.Label(controls, text="Preset:").grid(row=0, column=1, padx=(12, 4))
        self.preset_var = tk.StringVar(value="21")
        self.preset_combo = ttk.Combobox(
            controls,
            textvariable=self.preset_var,
            values=("21", "20", "1031", "1032", "1033", "1034", "1035", "1036"),
            state="readonly",
            width=10,
        )
        self.preset_combo.grid(row=0, column=2, pady=4)
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_changed)
        ttk.Button(controls, text="Connect", command=self._connect).grid(row=0, column=3, padx=4)
        ttk.Button(controls, text="Disconnect", command=self._disconnect).grid(row=0, column=4, padx=4)
        ttk.Button(controls, text="Refresh Config", command=self._request_configuration).grid(row=0, column=5, padx=6)
        ttk.Button(controls, text="Preset help", command=self._show_preset_help).grid(row=0, column=6, padx=6)
        controls.columnconfigure(7, weight=1)

        self.preset_hint_var = tk.StringVar(value=self._preset_summary(self.preset_var.get()))
        ttk.Label(main, textvariable=self.preset_hint_var, foreground="#666666", wraplength=760).pack(fill=tk.X, pady=(4, 2))

        device_frame = ttk.Frame(main)
        device_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(device_frame, text="Discovered headsets:").pack(anchor=tk.W)
        self.device_list = tk.Listbox(device_frame, height=5, exportselection=False)
        self.device_list.pack(fill=tk.X)

        self.status_var = tk.StringVar(value="Idle. Click Scan to discover headsets.")
        self.hr_var = tk.StringVar(value="<unknown>")
        self.hbo_var = tk.StringVar(value="<unknown>")
        self.hbr_var = tk.StringVar(value="<unknown>")
        self.eeg_channel_var = tk.StringVar(value='All')
        self.eeg_channel_scale_var = tk.DoubleVar(value=self.eeg_display_range)
        self._hr_history: Deque[float] = deque(maxlen=48)
        self._hr_filtered: Optional[float] = None
        self._last_hr_value: Optional[float] = None
        ttk.Label(main, textvariable=self.status_var).pack(fill=tk.X, pady=(6, 10))

        notebook = ttk.Notebook(main)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.summary_tab = ttk.Frame(notebook)
        self.metrics_tab = ttk.Frame(notebook)
        self.wave_tab = ttk.Frame(notebook)
        self.spectrum_tab = ttk.Frame(notebook)
        notebook.add(self.summary_tab, text="Summary")
        notebook.add(self.metrics_tab, text="Channel Metrics")
        notebook.add(self.wave_tab, text="Live Waveforms & Log")
        notebook.add(self.spectrum_tab, text="Power Spectrum")


        self._build_summary_tab()
        self._build_metrics_tab()
        self._build_wave_tab()
        self._build_spectrum_tab()

    def _build_summary_tab(self) -> None:
        left = ttk.Frame(self.summary_tab, padding=8)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.connection_state_var = tk.StringVar(value="DISCONNECTED")
        ttk.Label(left, text="Connection state:").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            left,
            textvariable=self.connection_state_var,
            font=("Segoe UI", 11, "bold"),
            foreground="#1c7ed6",
        ).grid(row=0, column=1, sticky=tk.W)

        self.model_var = tk.StringVar(value="<N/A>")
        self.preset_summary_var = tk.StringVar(value="<N/A>")
        self.eeg_rate_var = tk.StringVar(value="<unknown>")
        self.optics_rate_var = tk.StringVar(value="<unknown>")
        self.acc_rate_var = tk.StringVar(value="<unknown>")
        self.battery_var = tk.StringVar(value="<unknown>")
        self.notch_var = tk.StringVar(value="<unknown>")

        stats = (
            ("Model", self.model_var),
            ("Preset", self.preset_summary_var),
            ("EEG rate", self.eeg_rate_var),
            ("Optics rate", self.optics_rate_var),
            ("ACC rate", self.acc_rate_var),
            ("Notch filter", self.notch_var),
            ("Battery", self.battery_var),
        )
        for idx, (label, var) in enumerate(stats, start=1):
            ttk.Label(left, text=f"{label}:").grid(row=idx, column=0, sticky=tk.W, pady=2)
            ttk.Label(left, textvariable=var).grid(row=idx, column=1, sticky=tk.W, pady=2)

        right = ttk.LabelFrame(self.summary_tab, text="Configuration snapshot", padding=8)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        self.cfg_text = tk.Text(right, height=16, wrap=tk.WORD, bg="#f5f5f5", relief=tk.FLAT)
        self.cfg_text.pack(fill=tk.BOTH, expand=True)
        self.cfg_text.configure(state=tk.DISABLED)

    def _build_metrics_tab(self) -> None:
        frame = ttk.Frame(self.metrics_tab, padding=8)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Per-packet summary").pack(anchor=tk.W)
        self.packet_tree = ttk.Treeview(
            frame,
            columns=("rate", "channels", "description"),
            show="headings",
            height=10,
        )
        self.packet_tree.heading("rate", text="Packets/s")
        self.packet_tree.heading("channels", text="Channels")
        self.packet_tree.heading("description", text="Description")
        self.packet_tree.column("rate", width=90, anchor=tk.CENTER)
        self.packet_tree.column("channels", width=140)
        self.packet_tree.column("description", width=420)
        self.packet_tree.pack(fill=tk.BOTH, expand=True)
        self.packet_rows: Dict[str, str] = {}
        descriptions = {
            "EEG": "Raw EEG stream",
            "OPTICS": "Optics/fNIRS diodes",
            "PPG": "PPG sensors",
            "ACC": "Accelerometer",
            "GYRO": "Gyroscope",
            "BATTERY": "Battery telemetry",
            "DRL_REF": "DRL / reference",
        }
        for pkt in self.PACKET_ORDER:
            row = self.packet_tree.insert("", tk.END, values=("0.00", "--", descriptions.get(pkt, "")))
            self.packet_rows[pkt] = row

        ttk.Label(frame, text="Latest channel values").pack(anchor=tk.W, pady=(10, 0))
        self.channel_tree = ttk.Treeview(
            frame,
            columns=("packet", "channel", "value"),
            show="headings",
            height=12,
        )
        self.channel_tree.heading("packet", text="Packet")
        self.channel_tree.heading("channel", text="Channel")
        self.channel_tree.heading("value", text="Latest")
        self.channel_tree.column("packet", width=110)
        self.channel_tree.column("channel", width=150)
        self.channel_tree.column("value", width=160)
        self.channel_tree.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        derived = ttk.LabelFrame(frame, text="Derived metrics", padding=6)
        derived.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(derived, text="Heart rate:").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        ttk.Label(derived, textvariable=self.hr_var).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(derived, text="HbO delta (a.u.):").grid(row=1, column=0, sticky=tk.W, padx=(0, 8))
        ttk.Label(derived, textvariable=self.hbo_var).grid(row=1, column=1, sticky=tk.W)
        ttk.Label(derived, text="HbR delta (a.u.):").grid(row=2, column=0, sticky=tk.W, padx=(0, 8))
        ttk.Label(derived, textvariable=self.hbr_var).grid(row=2, column=1, sticky=tk.W)
        derived.columnconfigure(1, weight=1)

    def _build_wave_tab(self) -> None:
        top = ttk.Frame(self.wave_tab)
        top.pack(fill=tk.BOTH, expand=True)

        control = ttk.LabelFrame(top, text="Waveform scale", padding=(8, 4))
        control.pack(fill=tk.X, padx=8, pady=(8, 4))

        ttk.Label(control, text="EEG +/- (uV)").grid(row=0, column=0, sticky=tk.W)
        self.eeg_scale_combo = ttk.Combobox(
            control,
            values=self._eeg_scale_combo_values,
            state="readonly",
            width=8,
        )
        self.eeg_scale_combo.set(self._format_scale_value(self.eeg_display_range))
        self.eeg_scale_combo.grid(row=0, column=1, padx=(4, 12))
        self.eeg_scale_combo.bind("<<ComboboxSelected>>", self._handle_eeg_scale_change)

        ttk.Button(control, text="Auto scale", command=self._auto_scale_waveforms).grid(row=0, column=2, padx=(4, 12))
        ttk.Button(control, text="Reset", command=self._reset_scale).grid(row=0, column=3, padx=(0, 12))
        ttk.Checkbutton(
            control,
            text="Subtract DC offset",
            variable=self.detrend_var,
            command=lambda: self._queue_waveform_refresh(0),
        ).grid(row=0, column=4, sticky=tk.W)

        ttk.Label(control, text="EEG channel").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        self.eeg_channel_select = ttk.Combobox(
            control,
            textvariable=self.eeg_channel_var,
            state="readonly",
            width=12,
            values=("All",),
        )
        self.eeg_channel_select.grid(row=1, column=1, sticky=tk.W, pady=(6, 0))
        self.eeg_channel_select.bind("<<ComboboxSelected>>", self._on_eeg_channel_select)
        self.eeg_channel_spin = ttk.Spinbox(
            control,
            from_=1,
            to=2000,
            increment=1,
            textvariable=self.eeg_channel_scale_var,
            width=8,
        )
        self.eeg_channel_spin.grid(row=1, column=2, sticky=tk.W, padx=(12, 4), pady=(6, 0))
        ttk.Button(control, text="Apply", command=self._apply_eeg_channel_scale).grid(row=1, column=3, sticky=tk.W, pady=(6, 0))

        control.columnconfigure(4, weight=1)
        self._handle_eeg_scale_change()


        self.eeg_canvas = tk.Canvas(top, height=220, bg="#101010")
        self.eeg_canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))
        self.eeg_canvas.create_text(
            10,
            10,
            anchor=tk.NW,
            fill="#cccccc",
            text="EEG (uV)",
            font=("Segoe UI", 10, "bold"),
            tags="static",
        )

        self.optics_canvas = tk.Canvas(top, height=200, bg="#151515")
        self.optics_canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.optics_canvas.create_text(
            10,
            10,
            anchor=tk.NW,
            fill="#dddddd",
            text="Optics (uA)",
            font=("Segoe UI", 10, "bold"),
            tags="static",
        )

        log_frame = ttk.LabelFrame(self.wave_tab, text="Event log", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.log_text = tk.Text(log_frame, height=8, bg="#f0f0f0", wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)


    def _build_spectrum_tab(self) -> None:
        frame = ttk.Frame(self.spectrum_tab, padding=8)
        frame.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X, pady=(0, 8))
        reset_btn = ttk.Button(
            controls,
            text="Reset Averaging",
            command=lambda: self._reset_spectrum("Averaging reset. Waiting for data..."),
        )
        reset_btn.pack(side=tk.LEFT)
        if self.spectrum_status_var is None:
            self.spectrum_status_var = tk.StringVar(value="Waiting for data...")
        else:
            self.spectrum_status_var.set("Waiting for data...")
        ttk.Label(controls, textvariable=self.spectrum_status_var, foreground="#666666").pack(side=tk.LEFT, padx=(8, 0))

        self.spectrum_canvas = tk.Canvas(frame, height=360, bg="#181818")
        self.spectrum_canvas.pack(fill=tk.BOTH, expand=True)
        self.spectrum_canvas.create_text(
            10,
            10,
            anchor=tk.NW,
            fill="#dddddd",
            text="Averaged EEG power spectrum (0-70 Hz)",
            font=("Segoe UI", 10, "bold"),
            tags="static",
        )
        self._reset_spectrum()

    # --------------------- helpers ------------------------------
    def _scan_devices(self) -> None:
        if self.muse is None:
            return
        self.status_var.set("Scanning for Muse devices...")
        self.device_list.delete(0, tk.END)

        def worker() -> None:
            try:
                devices = self.muse.list_devices()
            except Exception as exc:
                self.event_queue.put(("error", f"Scan failed: {exc}"))
                return
            self.event_queue.put(("devices", devices))
            self.event_queue.put(("status", f"Found {len(devices)} device(s)."))
            self.event_queue.put(("event", f"Scan complete: {len(devices)} device(s)"))

        threading.Thread(target=worker, daemon=True).start()

    def _connect(self) -> None:
        if self.muse is None:
            return
        if self.connected:
            self.status_var.set("Already connected.")
            return
        selection = self.device_list.curselection()
        if not selection:
            messagebox.showinfo("Select a device", "Pick a headset from the list first.")
            return
        index = selection[0]
        preset = self.preset_var.get()
        self.status_var.set("Connecting...")

        def worker() -> None:
            try:
                self.muse.connect(index, self._on_data, preset=preset, on_state=self._on_state)
            except Exception as exc:
                self.event_queue.put(("error", f"Connect failed: {exc}"))
                return
            self.connected = True
            info = self.devices[index]
            msg = f"Connected to {info.name} ({info.mac}) preset {preset}"
            self.event_queue.put(("status", msg))
            self.event_queue.put(("event", msg))
            self.event_queue.put(("state", "CONNECTED"))
            self._kickoff_config_poll()

        threading.Thread(target=worker, daemon=True).start()

    def _disconnect(self) -> None:
        if self.muse is None or not self.connected:
            return
        try:
            self.muse.disconnect()
        except Exception as exc:
            self.event_queue.put(("error", f"Disconnect failed: {exc}"))
        finally:
            self.connected = False
            self.config = None
            self.channel_buffers.clear()
            self._reset_eeg_filter_state()
            self.latest_values.clear()
            self._reset_spectrum()
            self.connection_state = "DISCONNECTED"
            self.connection_state_var.set("DISCONNECTED")
            self._update_summary()
            self.event_queue.put(("status", "Disconnected."))
            self.event_queue.put(("event", "Disconnected."))

    def _kickoff_config_poll(self) -> None:
        if self.muse is None:
            return

        def poller() -> None:
            for _ in range(30):
                cfg = None
                try:
                    cfg = self.muse.get_configuration()
                except Exception:
                    cfg = None
                if cfg is not None:
                    self.event_queue.put(("config", cfg))
                    return
                time.sleep(0.3)

        threading.Thread(target=poller, daemon=True).start()

    def _request_configuration(self) -> None:
        if self.muse is None or not self.connected:
            return
        self._kickoff_config_poll()

    # ------------------- callbacks ------------------------------
    def _on_data(self, packet_type: str, timestamp: int, values: list) -> None:
        if not values:
            return
        now = time.time()
        self.sample_windows.setdefault(packet_type, deque(maxlen=512)).append(now)
        trimmed = [float(v) for v in values]
        try:
            self.data_queue.put_nowait((packet_type, timestamp, trimmed))
        except queue.Full:
            try:
                self.data_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.data_queue.put_nowait((packet_type, timestamp, trimmed))
            except queue.Full:
                pass

    def _on_state(self, state: str) -> None:
        self.event_queue.put(("event", f"State change: {state}"))
        self.event_queue.put(("state", state))

    # ------------------- event loop ------------------------------
    def _process_events(self) -> None:
        while True:
            try:
                kind, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "devices":
                self.devices = payload  # type: ignore[assignment]
                self.device_list.delete(0, tk.END)
                for idx, dev in enumerate(self.devices):
                    self.device_list.insert(tk.END, f"{idx}: {dev.name} ({dev.mac})")
            elif kind == "status":
                self.status_var.set(str(payload))
            elif kind == "error":
                messagebox.showerror("Muse error", str(payload))
                self._append_log(f"Error: {payload}")
            elif kind == "event":
                self._append_log(str(payload))
            elif kind == "state":
                state = str(payload)
                self.connection_state = state
                self.connection_state_var.set(state)
                if "CONNECTED" in state:
                    self.connected = True
                if state.startswith("DISCONNECTED"):
                    self.connected = False
            elif kind == "config":
                self.config = payload  # type: ignore[assignment]
                self._update_from_config()
                self._append_log("Configuration updated from device.")
                self._update_summary()

        new_packets: List[Tuple[str, int, List[float]]] = []
        eeg_updated = False
        while True:
            try:
                new_packets.append(self.data_queue.get_nowait())
            except queue.Empty:
                break

        for packet_type, timestamp, values in new_packets:
            numeric_values = [float(v) for v in values]
            self._ensure_channel_buffers(packet_type, len(numeric_values))
            if packet_type == "EEG":
                labels = self._channel_labels("EEG", len(numeric_values))
                numeric_values = [self._apply_eeg_lowpass(label, val) for label, val in zip(labels, numeric_values)]
                eeg_updated = True
            self.latest_values[packet_type] = (timestamp, numeric_values)
            buffers = self.channel_buffers[packet_type]
            for buf, val in zip(buffers, numeric_values):
                buf.append(val)
            self._update_channel_table(packet_type, timestamp, numeric_values)
        if new_packets:
            self._update_metrics()
            self._update_summary()
            if eeg_updated:
                self._update_spectrum_data()
        self._update_realtime_metrics()

        self.root.after(150, self._process_events)

    # ------------------- data helpers ---------------------------
    def _update_from_config(self) -> None:
        cfg = self.config
        if cfg is None:
            return
        sr = float(getattr(cfg, "output_frequency", 0) or 0)
        if sr:
            self.eeg_sample_rate = sr
        cutoff_value = getattr(cfg, "lowpass_filter", None)
        cutoff = self._coerce_lowpass_cutoff(cutoff_value)
        if cutoff is None:
            cutoff = self._coerce_lowpass_cutoff(getattr(cfg, "notch_filter", None))
        if cutoff is not None:
            self._lowpass_cutoff = cutoff
        enabled_attr = getattr(cfg, "lowpass_filter_enabled", None)
        if enabled_attr is None:
            enabled_attr = getattr(cfg, "notch_filter_enabled", None)
        if enabled_attr is not None:
            self._lowpass_enabled = bool(enabled_attr)
        elif cutoff is not None:
            self._lowpass_enabled = True
        self._configure_eeg_lowpass(self.eeg_sample_rate)

    def _ensure_channel_buffers(self, packet_type: str, count: int) -> None:
        buffers = self.channel_buffers.setdefault(packet_type, [])
        history = HISTORY_LENGTHS.get(packet_type, 256)
        current = len(buffers)
        if current == count:
            return
        if current > count:
            del buffers[count:]
            current = len(buffers)
        for _ in range(count - current):
            buffers.append(deque(maxlen=history))
        labels = self._channel_labels(packet_type, len(buffers))
        if packet_type == "EEG":
            for label in labels:
                self.eeg_channel_ranges.setdefault(label, max(self.eeg_display_range, 1.0))
                if label not in self._eeg_filter_state:
                    taps = self._eeg_filter_taps
                    if taps is not None:
                        self._eeg_filter_state[label] = np.zeros(len(taps), dtype=float)
                    else:
                        self._eeg_filter_state[label] = np.zeros(1, dtype=float)
        elif packet_type == "OPTICS":
            for label in labels:
                self.optics_channel_ranges.setdefault(label, max(self.optics_display_range, 0.1))
        self._refresh_channel_selector(packet_type, labels)

    def _packet_rate(self, packet_type: str) -> float:
        window = self.sample_windows.get(packet_type)
        if not window or len(window) < 2:
            return 0.0
        span = window[-1] - window[0]
        if span <= 0:
            return 0.0
        return len(window) / span

    def _channel_labels(self, packet_type: str, count: int) -> List[str]:
        if packet_type == "EEG":
            if self.config is not None:
                labels = MODEL_SPECIFIC_EEG.get(getattr(self.config, "model", ""))
                if labels and len(labels) >= count:
                    return labels[:count]
            return EEG_LABELS_BY_COUNT.get(count, [f"EEG{i + 1}" for i in range(count)])
        if packet_type == "OPTICS":
            return OPTICS_LABELS[:count]
        base = DEFAULT_CHANNEL_LABELS.get(packet_type)
        if base:
            return base[:count]
        return [f"{packet_type}{i + 1}" for i in range(count)]

    def _update_metrics(self) -> None:
        for pkt in self.PACKET_ORDER:
            row = self.packet_rows[pkt]
            rate = self._packet_rate(pkt)
            channels = len(self.latest_values[pkt][1]) if pkt in self.latest_values else 0
            description = self.packet_tree.item(row, "values")[2]
            self.packet_tree.item(row, values=(f"{rate:.2f}", channels, description))

    def _update_realtime_metrics(self) -> None:
        optics_buffers = self.channel_buffers.get("OPTICS")
        if not optics_buffers:
            self.hr_var.set("<unknown>")
            self.hbo_var.set("<unknown>")
            self.hbr_var.set("<unknown>")
            self._hr_filtered = None
            self._last_hr_value = None
            self._hr_history.clear()
            return
        labels = self._channel_labels("OPTICS", len(optics_buffers))
        label_to_buf = {label: optics_buffers[idx] for idx, label in enumerate(labels)}
        hr = self._estimate_heart_rate(label_to_buf)
        display_hr: Optional[float]
        if hr is not None:
            self._hr_history.append(hr)
            median_hr = float(np.median(self._hr_history))
            if self._hr_filtered is None:
                filtered = median_hr
            else:
                delta = median_hr - self._hr_filtered
                max_step = 5.0
                delta = max(-max_step, min(max_step, delta))
                filtered = self._hr_filtered + 0.25 * delta
            self._hr_filtered = filtered
            self._last_hr_value = filtered
            display_hr = filtered
        else:
            display_hr = self._hr_filtered
        if display_hr is not None:
            self.hr_var.set(f"{display_hr:.0f} bpm")
        else:
            self.hr_var.set("<unknown>")
        hbo, hbr = self._estimate_hemoglobin(label_to_buf)
        self.hbo_var.set(f"{hbo:+.3f}" if hbo is not None else "<unknown>")
        self.hbr_var.set(f"{hbr:+.3f}" if hbr is not None else "<unknown>")

    def _estimate_heart_rate(self, optics_buffers: Dict[str, Deque[float]]) -> Optional[float]:
        fs = self._packet_rate("OPTICS")
        if fs <= 5.0:
            return None
        candidate_labels = ["Optics9", "Optics10", "Optics13", "Optics14", "Optics5", "Optics6", "Optics1", "Optics2"]
        hr_estimates: List[float] = []
        for label in candidate_labels:
            buf = optics_buffers.get(label)
            if not buf:
                continue
            arr = np.asarray(buf, dtype=float)
            hr_val = self._heart_rate_from_buffer(arr, fs)
            if hr_val is not None:
                hr_estimates.append(hr_val)
        if not hr_estimates:
            return None
        median_hr = float(np.median(hr_estimates))
        previous = self._last_hr_value
        if previous is not None:
            allowed_delta = 30.0
            close = [val for val in hr_estimates if abs(val - previous) <= allowed_delta]
            if close:
                median_hr = float(np.median(close))
            elif abs(median_hr - previous) > allowed_delta:
                return None
        return median_hr

    def _heart_rate_from_buffer(self, arr: np.ndarray, fs: float) -> Optional[float]:
        if fs <= 0.0:
            return None
        if arr.size < int(fs * 6):
            return None
        max_window = int(fs * 12)
        if arr.size > max_window:
            arr = arr[-max_window:]
        arr = np.asarray(arr, dtype=float)
        arr = arr - np.median(arr)
        if np.max(np.abs(arr)) <= 1e-6:
            return None
        smooth_len = max(int(fs * 0.75), 5)
        if smooth_len % 2 == 0:
            smooth_len += 1
        kernel = np.ones(smooth_len) / smooth_len
        baseline = np.convolve(arr, kernel, mode="same")
        arr_hp = arr - baseline
        if np.max(np.abs(arr_hp)) <= 1e-6:
            arr_hp = arr
        window = np.hanning(arr_hp.size)
        spec = np.fft.rfft(arr_hp * window)
        freqs = np.fft.rfftfreq(arr_hp.size, d=1.0 / fs)
        band = (freqs >= 0.6) & (freqs <= 3.5)
        if not np.any(band):
            return None
        mag = np.abs(spec)[band]
        freq_band = freqs[band]
        if mag.size == 0:
            return None
        noise_floor = np.median(mag)
        peak_idx = int(np.argmax(mag))
        peak_power = float(mag[peak_idx])
        if not np.isfinite(peak_power) or peak_power <= 0:
            return None
        if noise_floor <= 0 or peak_power / (noise_floor + 1e-9) < 3.0:
            return None
        left = max(0, peak_idx - 2)
        right = min(mag.size, peak_idx + 3)
        local_mag = mag[left:right]
        local_freqs = freq_band[left:right]
        if local_mag.size == 0:
            return None
        weighted_sum = float(np.sum(local_mag * local_freqs))
        weight_total = float(np.sum(local_mag))
        if weight_total <= 0.0:
            return None
        peak_freq = weighted_sum / weight_total
        bpm = peak_freq * 60.0
        if not np.isfinite(bpm) or bpm <= 35.0 or bpm >= 190.0:
            return None
        return bpm


    def _estimate_hemoglobin(self, optics_buffers: Dict[str, Deque[float]]) -> Tuple[Optional[float], Optional[float]]:
        pairs = [("Optics1", "Optics3"), ("Optics2", "Optics4"), ("Optics5", "Optics7"), ("Optics6", "Optics8")]
        hbo_values: List[float] = []
        hbr_values: List[float] = []
        eps = 1e-6
        for ch730, ch850 in pairs:
            buf730 = optics_buffers.get(ch730)
            buf850 = optics_buffers.get(ch850)
            if not buf730 or not buf850:
                continue
            arr730 = np.asarray(buf730, dtype=float)
            arr850 = np.asarray(buf850, dtype=float)
            n = min(arr730.size, arr850.size)
            if n < 10:
                continue
            arr730 = arr730[-n:]
            arr850 = arr850[-n:]
            mean730 = np.mean(arr730) + eps
            mean850 = np.mean(arr850) + eps
            od730 = -np.log(np.clip(arr730 / mean730, eps, None))
            od850 = -np.log(np.clip(arr850 / mean850, eps, None))
            hbo_values.append(float(np.mean(od850)))
            hbr_values.append(float(np.mean(od730)))
        if not hbo_values:
            return (None, None)
        return (float(np.mean(hbo_values)), float(np.mean(hbr_values)))

    def _update_channel_table(self, packet_type: str, timestamp: int, values: List[float]) -> None:
        # rebuild table each time
        self.channel_tree.delete(*self.channel_tree.get_children())
        for pkt in self.PACKET_ORDER:
            entry = self.latest_values.get(pkt)
            if not entry:
                continue
            _, vals = entry
            labels = self._channel_labels(pkt, len(vals))
            if pkt == "EEG":
                base = max(self.eeg_display_range, 1.0)
                for lbl in labels:
                    self.eeg_channel_ranges.setdefault(lbl, base)
            elif pkt == "OPTICS":
                base = max(self.optics_display_range, 0.1)
                for lbl in labels:
                    self.optics_channel_ranges.setdefault(lbl, base)
            self._refresh_channel_selector(pkt, labels)
            unit = PACKET_UNITS.get(pkt, "")
            for label, val in zip(labels, vals):
                formatted = f"{val:.3f}" if abs(val) < 1e6 else f"{val:.3e}"
                if unit:
                    formatted = f"{formatted} {unit}"
                self.channel_tree.insert("", tk.END, values=(pkt, label, formatted))

    def _append_log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _preset_summary(self, preset: str) -> str:
        info = PRESET_SUMMARIES.get(preset)
        if info:
            return f"{preset}: {info}"
        return f"Preset {preset}: see preset help for details."

    def _on_preset_changed(self, _event=None) -> None:
        if self.preset_hint_var is not None:
            self.preset_hint_var.set(self._preset_summary(self.preset_var.get()))

    def _show_preset_help(self) -> None:
        top = tk.Toplevel(self.root)
        top.title("Muse presets")
        top.resizable(False, False)
        frame = ttk.Frame(top, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        text = tk.Text(frame, width=80, height=18, wrap=tk.WORD, bg="#fdfdfd")
        text.insert(tk.END, PRESET_HELP_TEXT)
        text.configure(state=tk.DISABLED)
        text.pack(fill=tk.BOTH, expand=True)
        ttk.Button(frame, text="Close", command=top.destroy).pack(pady=(6, 0))

    def _update_summary(self) -> None:
        cfg = self.config
        if cfg is None:
            self.model_var.set("<N/A>")
            self.preset_summary_var.set(self.preset_var.get())
            if self.preset_hint_var is not None:
                self.preset_hint_var.set(self._preset_summary(self.preset_var.get()))
            self.eeg_rate_var.set("<unknown>")
            self.optics_rate_var.set("<unknown>")
            self.acc_rate_var.set("<unknown>")
            self.battery_var.set("<unknown>")
            self.notch_var.set("<unknown>")
        else:
            self.model_var.set(getattr(cfg, "model", "<unknown>"))
            preset = getattr(cfg, "preset", self.preset_var.get())
            self.preset_summary_var.set(self._preset_summary(str(preset)))
            self.eeg_rate_var.set(f"{getattr(cfg, 'output_frequency', 0)} Hz")
            optics_rate = getattr(cfg, 'downsample_rate', None)
            self.optics_rate_var.set(f"{optics_rate} Hz" if optics_rate else "<unknown>")
            acc_rate = getattr(cfg, 'accelerometer_sample_frequency', None)
            self.acc_rate_var.set(f"{acc_rate} Hz" if acc_rate else "<unknown>")
            notch_enabled = getattr(cfg, 'notch_filter_enabled', None)
            notch = getattr(cfg, 'notch_filter', None)
            self.notch_var.set(f"{notch} ({'on' if notch_enabled else 'off'})" if notch is not None else "<unknown>")
            battery = getattr(cfg, 'battery_percent_remaining', None)
            if battery is not None:
                self.battery_var.set(f"{battery:.1f}%")
            else:
                self.battery_var.set("<unknown>")
            if self.preset_hint_var is not None:
                self.preset_hint_var.set(self._preset_summary(str(preset)))
        self._update_config_text()

    def _update_config_text(self) -> None:
        self.cfg_text.configure(state=tk.NORMAL)
        self.cfg_text.delete("1.0", tk.END)
        cfg = self.config
        if cfg is None:
            text = "<No configuration captured yet. Click Refresh Config after connecting>."
        else:
            fields = [
                "preset", "model", "headband_name", "bluetooth_mac", "serial_number",
                "headset_serial_number", "microcontroller_id", "eeg_channel_count",
                "output_frequency", "downsample_rate", "accelerometer_sample_frequency",
                "drl_ref_frequency", "battery_data_enabled", "drl_ref_enabled",
                "notch_filter", "notch_filter_enabled", "afe_gain", "serout_mode",
                "adc_frequency", "battery_percent_remaining",
            ]
            lines = ["MuseConfigurationInfo:"]
            for field in fields:
                lines.append(f"  {field}: {getattr(cfg, field, None)}")
            text = "\n".join(lines)
        self.cfg_text.insert(tk.END, text)
        self.cfg_text.configure(state=tk.DISABLED)

    def _reset_scale(self) -> None:
        self.eeg_display_range = 200.0
        self.optics_display_range = 12.0
        if self.eeg_scale_combo is not None:
            self._ensure_combo_has_value(self.eeg_scale_combo, self.eeg_display_range)
        self._set_all_channel_ranges("EEG", self.eeg_display_range)
        self._set_all_channel_ranges("OPTICS", self.optics_display_range)
        self._on_eeg_channel_select()
        self._queue_waveform_refresh(0)

    def _current_eeg_range(self) -> float:
        return float(self.eeg_display_range)

    def _current_optics_range(self) -> float:
        return float(self.optics_display_range)

    @staticmethod
    def _format_scale_value(value: float) -> str:
        formatted = f"{value:.3f}"
        formatted = formatted.rstrip('0').rstrip('.')
        return formatted if formatted else '0'

    def _ensure_combo_has_value(self, combo: Optional[ttk.Combobox], value: float) -> None:
        if combo is None:
            return
        label = self._format_scale_value(value)
        raw_values = combo.cget('values')
        if isinstance(raw_values, str):
            current = [raw_values]
        else:
            current = list(raw_values) if raw_values else []
        if label not in current:
            numeric_values = []
            for entry in current:
                try:
                    numeric_values.append(float(entry))
                except (TypeError, ValueError):
                    continue
            numeric_values.append(value)
            numeric_values = sorted(set(numeric_values))
            combo.configure(values=tuple(self._format_scale_value(v) for v in numeric_values))
        combo.set(label)

    def _coerce_scale_value(
        self,
        combo: Optional[ttk.Combobox],
        minimum: float,
        fallback: float,
    ) -> float:
        if combo is None:
            return float(fallback)
        raw = combo.get()
        try:
            value = float(raw)
        except Exception:
            value = float(fallback)
        value = max(minimum, value)
        self._ensure_combo_has_value(combo, value)
        return value

    def _update_scale_from_ui(self) -> None:
        self.eeg_display_range = self._coerce_scale_value(self.eeg_scale_combo, 1.0, self.eeg_display_range)


    def _handle_eeg_scale_change(self, *_: object) -> None:
        self._update_scale_from_ui()
        self._set_all_channel_ranges("EEG", self.eeg_display_range)
        self._on_eeg_channel_select()
        self._queue_waveform_refresh(0)



    def _set_all_channel_ranges(self, packet_type: str, value: float) -> None:
        store = self.eeg_channel_ranges if packet_type == "EEG" else self.optics_channel_ranges
        min_range = 1.0 if packet_type == "EEG" else 0.1
        new_value = max(float(value), min_range)
        for key in list(store.keys()):
            store[key] = new_value


    def _configure_eeg_lowpass(self, fs: float) -> None:
        if not self._lowpass_enabled:
            self._eeg_filter_taps = None
            self._reset_eeg_filter_state()
            return
        cutoff = float(self._lowpass_cutoff)
        nyquist = fs / 2.0 if fs > 0 else 0.0
        if fs <= 0 or cutoff <= 0 or cutoff >= nyquist:
            self._eeg_filter_taps = None
            self._reset_eeg_filter_state()
            return
        num_taps = 97 if fs <= 512 else 129
        self._eeg_filter_taps = self._design_lowpass_taps(fs, cutoff, num_taps)
        self._reset_eeg_filter_state()

    def _reset_eeg_filter_state(self) -> None:
        taps = self._eeg_filter_taps
        state: Dict[str, np.ndarray] = {}
        if taps is None:
            self._eeg_filter_state = state
            return
        length = len(taps)
        buffers = self.channel_buffers.get("EEG")
        if buffers:
            labels = self._channel_labels("EEG", len(buffers))
            for label in labels:
                state[label] = np.zeros(length, dtype=float)
        self._eeg_filter_state = state

    def _apply_eeg_lowpass(self, label: str, value: float) -> float:
        taps = self._eeg_filter_taps
        if taps is None:
            return value
        buf = self._eeg_filter_state.get(label)
        if buf is None or len(buf) != len(taps):
            buf = np.zeros(len(taps), dtype=float)
        buf[:-1] = buf[1:]
        buf[-1] = value
        self._eeg_filter_state[label] = buf
        return float(np.dot(taps, buf))

    @staticmethod
    def _coerce_lowpass_cutoff(value: object) -> Optional[float]:
        if value is None:
            return None
        cutoff: Optional[float]
        if isinstance(value, (int, float)):
            cutoff = float(value)
        elif isinstance(value, str):
            cleaned = ''.join(ch for ch in value if (ch.isdigit() or ch == '.'))
            if not cleaned:
                return None
            try:
                cutoff = float(cleaned)
            except ValueError:
                return None
        else:
            return None
        if not math.isfinite(cutoff) or cutoff <= 0:
            return None
        if cutoff < 10.0:
            return 10.0
        if cutoff > 120.0:
            return 120.0
        return cutoff


    @staticmethod
    def _design_lowpass_taps(fs: float, cutoff: float, num_taps: int) -> np.ndarray:
        taps = max(5, int(num_taps))
        if taps % 2 == 0:
            taps += 1
        m = taps - 1
        n = np.arange(taps) - m / 2.0
        norm_cutoff = cutoff / fs
        sinc_arg = 2.0 * norm_cutoff * n
        kernel = 2.0 * norm_cutoff * np.sinc(sinc_arg)
        window = np.hamming(taps)
        coeffs = kernel * window
        sum_coeffs = np.sum(coeffs)
        if not np.isfinite(sum_coeffs) or sum_coeffs == 0.0:
            return np.zeros(taps, dtype=float)
        return (coeffs / sum_coeffs).astype(float)

