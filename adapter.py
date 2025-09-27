import threading
from typing import List, Optional

try:
    from muse_py import Muse as _Muse
except Exception as _e:  # pragma: no cover
    _Muse = None


class MuseEEGAdapter:
    """
    Minimal adapter that exposes an EEGDataHandler-like interface using the Muse wrapper.

    Intended to drop into the old working visualizer with minimal code changes:
    - fields: sampling_rate, channels, num_channels, time_scale, window_size,
              y_data (list[list[float]]), index, buffer_filled, data_lock
    - methods: start_stream(), is_sampling_rate_known(), change_time_scale(new)
    """

    def __init__(self, time_scale: float = 10.0, preset: str = "21", device_index: int = 0):
        if _Muse is None:
            raise RuntimeError(
                "Muse wrapper not found. Build it and ensure muse_py/bin has muse_wrapper.pyd + libmuse.dll"
            )
        self.time_scale = time_scale
        self.preset = preset
        self.device_index = device_index

        self.sampling_rate: Optional[float] = None
        self.channels: List[str] = [f"EEG{i+1}" for i in range(6)]
        self.num_channels = len(self.channels)

        self.window_size: int = 0
        self.y_data: Optional[List[List[float]]] = None
        self.index: int = 0
        self.buffer_filled: bool = False
        self.data_lock = threading.Lock()

        self._last_configuration: Optional[object] = None
        self._muse = _Muse()

    # ---------- lifecycle ----------
    def start_stream(self) -> None:
        def on_data(packet_type: str, ts: int, values: list) -> None:
            if packet_type != 'EEG':
                return
            if self.sampling_rate is None:
                cfg = None
                try:
                    cfg = self._muse.get_configuration()
                except Exception:
                    cfg = None
                reported_rate = 0.0
                if cfg is not None:
                    self._last_configuration = cfg
                    reported_rate = float(
                        getattr(cfg, "output_frequency", 0)
                        or getattr(cfg, "adc_frequency", 0)
                        or 0.0
                    )
                self.sampling_rate = reported_rate or 256.0
                with self.data_lock:
                    self.window_size = max(1, int(self.sampling_rate * max(self.time_scale, 0.1)))
                    channel_count = len(values) or (
                        getattr(cfg, "eeg_channel_count", 0) if cfg is not None else 0
                    ) or self.num_channels
                    self.num_channels = channel_count
                    self.channels = [f"EEG{i+1}" for i in range(self.num_channels)]
                    self.y_data = [[0.0] * self.window_size for _ in range(self.num_channels)]
                    self.index = 0
                    self.buffer_filled = False
            with self.data_lock:
                if not self.y_data:
                    return
                n = min(self.num_channels, len(values))
                for i in range(n):
                    self.y_data[i][self.index] = float(values[i])
                self.index = (self.index + 1) % self.window_size
                if self.index == 0:
                    self.buffer_filled = True

        self._muse.connect(self.device_index, on_data, preset=self.preset)

    def is_sampling_rate_known(self) -> bool:
        return self.sampling_rate is not None

    def change_time_scale(self, new_time_scale: float) -> None:
        with self.data_lock:
            if self.sampling_rate is None:
                self.time_scale = new_time_scale
                return
            self.time_scale = new_time_scale
            new_ws = max(1, int(self.sampling_rate * self.time_scale))
            if not self.y_data:
                self.window_size = new_ws
                self.y_data = [[0.0] * new_ws for _ in range(self.num_channels)]
                self.index = 0
                self.buffer_filled = False
                return
            new_y = [[0.0] * new_ws for _ in range(self.num_channels)]
            for ch in range(self.num_channels):
                data = self.y_data[ch]
                seq = data[self.index:] + data[:self.index]
                seq = seq[-new_ws:]
                new_y[ch] = list(seq)
            self.y_data = new_y
            self.window_size = new_ws
            self.index = min(self.index, new_ws - 1)
            self.buffer_filled = self.index == 0

    @property
    def last_configuration(self) -> Optional[object]:
        """Return the most recent configuration snapshot fetched from the Muse client."""

        return self._last_configuration
