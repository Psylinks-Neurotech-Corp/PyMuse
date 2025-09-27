# Muse Py Wrapper

A Python-first interface to the Interaxon Muse Windows SDK (`libmuse`) that lets you scan for headsets, connect, stream EEG/ACC/Gyro/PPG/Optical/Battery data, and visualize everything with a rich Tk GUI. The bindings are implemented with a `pybind11` C++ extension and ship with batteries included: build scripts, demo apps, and helper tools for research or rapid prototyping.

## Highlights

- **Feature-complete bindings** – expose discovery, connection management, packet streaming, device configuration lookups, and preset selection directly in Python.
- **Live dashboard** – `examples/gui_stream_demo.py` displays packet rates, channel metrics, derived HR/HbO/HbR indicators, per-channel scaling, and spectrum plots.
- **Optics + EEG ready** – Presets (`21`, `1031`–`1036`) cover pure EEG and combined fNIRS (optics) use-cases; the GUI auto-tunes ranges for optics channels.
- **Windows toolchain friendly** – scripts handle the `libmuse.dll` copies, Visual Studio/MSBuild invocation, and pybind11 build configuration.
- **GPLv3 licensed** – open improvements welcome; see [LICENSE](LICENSE).

## Prerequisites

| Component | Notes |
|-----------|-------|
| Windows 10/11 x64 | 64-bit only (matches the Muse SDK) |
| Visual Studio 2019/2022 | Install the *Desktop development with C++* workload |
| CMake >= 3.20 | Used to configure/build the extension |
| Python 3.9+ (x64) | Use the interpreter you plan to run with |

The Muse SDK (libmuse 8.0.5) is vendored under `libmuse_windows_8.0.5/libmuse_windows_8.0.5`.

## Building the extension

```powershell
# Developer PowerShell for VS (matching your Python architecture)
cd C:\Users\Prabha\Desktop\PsyLinks Tech\muse_py

$python = "C:\\path\\to\\python.exe"   # e.g. C:\Users\Prabha\miniconda3\python.exe
$libmuse = "libmuse_windows_8.0.5/libmuse_windows_8.0.5"

cmake -S . -B build -DMUSE_SDK_ROOT=$libmuse -DPython3_EXECUTABLE=$python
cmake --build build --config Release
```

Artifacts land in `build/python/Release/`:

```
build/python/Release/muse_wrapper.cp3xx-win_amd64.pyd
build/python/Release/libmuse.dll
```

Place that directory on `PYTHONPATH` or copy the `.pyd` (and accompanying `libmuse.dll`) next to your application.

## Quick-start (Python API)

```python
from muse_py import Muse

muse = Muse()

for idx, device in enumerate(muse.list_devices()):
    print(idx, device.name, device.mac)

def on_packet(packet_type, timestamp, values):
    if packet_type == "EEG":
        process_eeg(values)  # your handler here
    elif packet_type == "BATTERY":
        print(f"Battery remaining: {values[0]:.1f}%")

muse.connect(device_index=0, callback=on_packet, preset="1035")

config = muse.get_configuration()
print(f"Connected to {config.model} @ {config.output_frequency} Hz using preset {config.preset}")
```

Packet types currently forwarded to Python callbacks:

- `EEG`, `OPTICS`, `PPG`
- `ACC`, `GYRO`
- `BATTERY`
- `DRL_REF`

Callbacks are invoked from a background thread started by `Muse::run_asynchronously()`; coordinate with your UI or async code accordingly.

## GUI demo

```powershell
# After the extension is built and on PYTHONPATH
python examples/gui_stream_demo.py
```

The demo provides:

- Device discovery, preset picker, and connection controls.
- Live packet rate monitor and latest values table.
- Per-channel scaling (manual & auto) for EEG/Optics traces.
- Derived metrics: smoothed BPM, HbO/HbR deltas.
- Power spectrum view using the FIR low-pass filtered EEG stream.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ImportError: No module named 'muse_py'` | Add `build/python/Release` to `PYTHONPATH` or copy the `.pyd` next to your script. |
| Linker can’t find `libmuse-wrt.lib` | Ensure `-DMUSE_SDK_ROOT` points at the directory containing `include/api` and `lib/release/x64`. |
| No devices discoverable | Turn on the headset, confirm Bluetooth is enabled, and rerun **Scan**. |
| Optics traces look flat | Hit **Auto Scale**, then tweak per-channel range (sub-uA options are available). |

## Repo structure

```
examples/                # GUI demo & sample scripts
src/                     # pybind11 extension sources
build_wrapper.ps1        # PowerShell helper to configure+build
BUILD_MUSE.md            # Legacy build notes (kept for reference)
LICENSE                  # GPLv3 license
README.md                # You are here
```

## Keeping up to date

1. Pull latest changes: `git pull`
2. Re-run `cmake --build build --config Release`
3. Restart your Python session to reload the `.pyd`

## Packaging roadmap

- **PyPI**: once the Python package metadata (`pyproject.toml`, versioning, wheels) is finalized we can publish via `python -m build` + `twine upload`.
- **conda-forge**: after the PyPI release, draft a feedstock recipe pointing to the sdist/wheel so the community can `conda install muse-py`.

## Contributing

Issues and PRs are welcome! Please:

1. Open an issue describing bugs or feature requests.
2. Create a topic branch, run the GUI demo/tests.
3. Ensure formatting stays consistent (PEP 8 / clang-format for C++ where applicable).

## License

Released under the [GNU General Public License v3.0](LICENSE).

Interaxon, Muse, and other trademarks belong to their respective owners. This project is an independent community effort and is not affiliated with Interaxon.
