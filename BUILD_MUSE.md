Muse Windows Wrapper (pybind11) — Build & Plug‑in

What this gives you
- A native extension wrapping Interaxon’s libmuse (Windows) to stream Muse EEG/ACC/PPG/OPTICS directly.
- Clean handoff: compiled artifacts live in `muse_py/bin` and the Python package auto‑loads from there.
- Optional adapter (`MuseEEGAdapter`) that mimics your old `EEGDataHandler` for drop‑in use.

Folder contents
- `muse_py/src/muse_wrapper.cpp`  C++ pybind11 bindings
- `muse_py/CMakeLists.txt`        Build script (copies outputs to `muse_py/bin`)
- `muse_py/bin/`                  Final `.pyd` + `libmuse.dll` (after build)
- `muse_py/__init__.py`           Python loader (adds `bin` to `sys.path`)
- `muse_py/adapter.py`            Optional drop‑in replacement for `EEGDataHandler`
- `muse_py/build_wrapper.ps1`     One‑click build script

Prereqs
- Windows 10/11 x64
- Visual Studio 2022 (Desktop development with C++)
- CMake 3.20+
- Python 3.9+ 64‑bit
- SDK is vendored at: `libmuse_windows_8.0.5/libmuse_windows_8.0.5`

Build (one time)
Option A — helper script
1) Open “x64 Native Tools Command Prompt for VS 2022”
2) `cd muse_py`
3) `powershell -ExecutionPolicy Bypass -File .\build_wrapper.ps1 -PythonExe "C:\\Path\\To\\python.exe"`

Option B — manual
1) `cd muse_py`
2) `cmake -S . -B build -G "Visual Studio 17 2022" -A x64 -DMUSE_SDK_ROOT=..\libmuse_windows_8.0.5\libmuse_windows_8.0.5 -DPython3_EXECUTABLE="C:\\Path\\To\\python.exe"`
3) `cmake --build build --config Release`

Artifacts
- `muse_py/bin/muse_wrapper.cp3xx-win_amd64.pyd`
- `muse_py/bin/libmuse.dll`

Plug‑and‑play in the old visualizer
Minimal (direct API):
```
from muse_py import Muse
m = Muse()
devs = m.list_devices()
m.connect(0, on_data, preset='21')  # on_data(type:str, ts_us:int, values:list[float])
```

Drop‑in (adapter mimics EEGDataHandler):
```
from muse_py.adapter import MuseEEGAdapter as EEGDataHandler

handler = EEGDataHandler(preset='21')  # or '1035' for optics-enabled modes
handler.start_stream()
# existing code: wait for handler.is_sampling_rate_known(), then use handler.y_data, handler.index, etc.
```

Notes
- Keep `muse_wrapper.pyd` and `libmuse.dll` together in `muse_py/bin`.
- The adapter is optional. It exists only to make migration trivial; you can drop it if not needed.
- Presets: `'21'` EEG‑only; `'1031'..'1036'` EEG + Optics (availability depends on device).

Troubleshooting
- ImportError: ensure `muse_py/bin` contains both `.pyd` and `libmuse.dll` (build copies them there).
- Link error: set `-DMUSE_SDK_ROOT` to `libmuse_windows_8.0.5/libmuse_windows_8.0.5` (folder with `include/api` and `lib/release/x64`).
- No devices: ensure the headset is on + paired in Windows Bluetooth; then call `list_devices()`.
