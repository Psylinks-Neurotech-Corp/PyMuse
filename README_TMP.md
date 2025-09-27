Muse Python Wrapper (Windows)

Overview
- Wraps Interaxon Muse Windows SDK (libmuse) via pybind11 C++ extension.
- Exposes scan, connect, and data callbacks for EEG/ACC/GYRO/PPG/OPTICS/BATTERY/DRL (fNIRS).
- Produces a `muse_wrapper.pyd` that Python can import.
- Provides access to headband configuration (model, preset, sample rates, battery, notch).

Prereqs
- Windows 10/11 x64
- Visual Studio 2019/2022 (with C++ toolchain)
- CMake 3.20+
- Python 3.9+ (same architecture as toolchain, x64)

SDK
- Already vendored here: `libmuse_windows_8.0.5/libmuse_windows_8.0.5`

Build
1) Open a Developer PowerShell (matching your Python architecture, e.g., x64)
2) From the repo root:
   - `cd muse_py`
   - `cmake -S . -B build -DMUSE_SDK_ROOT=../libmuse_windows_8.0.5/libmuse_windows_8.0.5 -DPython3_EXECUTABLE=path\to\python.exe`
   - `cmake --build build --config Release`
3) Find the extension in `muse_py/build/python/muse_wrapper.pyd`.
   Copy/append that directory to your `PYTHONPATH` or place next to your app.

Use
```
from muse_py import Muse

m = Muse()
devs = m.list_devices()
for i, d in enumerate(devs):
    print(i, d)

def on_data(t, ts, vals):
    if t == 'EEG':
        pass  # handle EEG samples
    elif t == 'BATTERY':
        print(f"Battery %: {vals[0]:.1f}")

m.connect(0, on_data, preset='1035')  # EEG + Optics
cfg = m.get_configuration()
if cfg:
    print(f"Connected to {cfg.model} preset {cfg.preset} @ {cfg.output_frequency} Hz")
```

Notes
- Connection state callbacks now surface transitions like `DISCONNECTED->CONNECTED`.
- The wrapper uses `Muse::run_asynchronously()`; data callbacks arrive on a background thread.
- Streams EEG, ACC, GYRO, PPG, OPTICS, BATTERY, and DRL_REF packets into Python callbacks (GUI plots EEG with a 0.5–50 Hz band-pass filter and shows optics/fNIRS currents).
- Presets:
  - `'21'`: EEG default (2016+), no optics
  - `'1031'..'1036'`: EEG + Optics variants (per SDK docs; availability depends on model)
- Ensure `libmuse.dll` resides next to `muse_wrapper.pyd` (CMake copies it to the output folder).

Troubleshooting
- ImportError: set `PYTHONPATH` to `muse_py/build/python` or copy `muse_wrapper.pyd` into your app folder.
- Link errors: verify `MUSE_SDK_ROOT` points to the `libmuse_windows_8.0.5/libmuse_windows_8.0.5` dir.
- No devices found: ensure the headset is on and paired/advertising; Windows Bluetooth must be enabled.

- GUI demo: `python muse_py/examples/gui_stream_demo.py` opens an interactive dashboard with device configuration, per-packet rates, dynamic channel values (EEG/ACC/Gyro/PPG/Optics/Battery/DRL), and live EEG/Optics waveforms.





