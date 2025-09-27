"""
High-level Python API over the native muse_wrapper extension.

- Scans and connects to Muse headbands
- Streams EEG/Optics/ACC/PPG/Gyro/Battery/DRL packets via callbacks

This module attempts to locate the built extension automatically in
"muse_py/build/python" so you don't have to tweak PYTHONPATH manually.
"""
from __future__ import annotations

import os
import sys
from typing import Callable, List, Optional


def _ensure_extension_on_path() -> None:
    here = os.path.dirname(__file__)
    candidates = [
        os.path.join(here, "bin"),
        os.path.join(here, "build", "python"),
        os.path.join(here, "build", "python", "Release"),
        os.path.join(here, "build", "python", "Debug"),
    ]
    for path in candidates:
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)


_ensure_extension_on_path()

try:
    import muse_wrapper as _native
except Exception as exc:  # pragma: no cover
    _native = None
    _NativeSession = None
    _NativeConfig = None
    _import_error = exc
else:
    _NativeSession = getattr(_native, "MuseSession", None)
    _NativeConfig = getattr(_native, "MuseConfigurationInfo", None)
    if _NativeSession is None:
        _import_error = ImportError("MuseSession missing from muse_wrapper")
    else:
        _import_error = None


if _NativeConfig is not None:
    MuseConfigurationInfo = _NativeConfig  # type: ignore[assignment]
else:  # pragma: no cover
    class MuseConfigurationInfo:  # minimal stub when native extension lacks it
        pass


class DeviceInfo:
    def __init__(self, name: str, mac: str) -> None:
        self.name = name
        self.mac = mac

    def __repr__(self) -> str:  # pragma: no cover
        return f"DeviceInfo(name={self.name!r}, mac={self.mac!r})"


class Muse:
    """High-level convenience wrapper over muse_wrapper.MuseSession."""

    def __init__(self) -> None:
        if _NativeSession is None or _import_error is not None:
            raise RuntimeError(
                "muse_wrapper extension not found. Build it via CMake. Original error: "
                + repr(_import_error)
            )
        self._sess = _NativeSession()
        self._on_data: Optional[Callable[[str, int, list], None]] = None
        self._on_state: Optional[Callable[[str], None]] = None
        self._last_configuration: Optional[MuseConfigurationInfo] = None

    def list_devices(self) -> List[DeviceInfo]:
        devices = self._sess.list_devices()
        return [DeviceInfo(d.name, d.mac) for d in devices]

    def connect(
        self,
        index: int,
        on_data: Callable[[str, int, list], None],
        preset: str = "auto",
        on_state: Callable[[str], None] | None = None,
    ) -> None:
        self._on_data = on_data
        self._on_state = on_state or (lambda _evt: None)
        self._last_configuration = None
        self._sess.connect_index(index, self._on_data, self._on_state, preset)

    def disconnect(self) -> None:
        self._sess.disconnect()

    @property
    def is_connected(self) -> bool:
        return bool(self._sess.is_connected())

    def get_configuration(self) -> Optional[MuseConfigurationInfo]:
        if not hasattr(self._sess, "get_configuration"):
            return None
        cfg = self._sess.get_configuration()
        if cfg is not None:
            self._last_configuration = cfg
        return cfg

    @property
    def last_configuration(self) -> Optional[MuseConfigurationInfo]:
        return self._last_configuration


__all__ = ["Muse", "DeviceInfo", "MuseConfigurationInfo"]
