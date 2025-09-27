from muse_py import Muse
import time

m = Muse()
devices = m.list_devices()
if not devices:
    print("No Muse devices found. Put the headset in pairing/advertising mode and try again.")
    raise SystemExit(1)

for i, d in enumerate(devices):
    print(i, d)

def on_data(t, ts, values):
    # Print a quick summary per type
    if t == 'EEG':
        print(f"EEG @ {ts}: {values[:4]} ...")
    elif t == 'OPTICS':
        print(f"OPTICS @ {ts}: {values[:4]} ...")

print("Connecting to first device with EEG+Optics preset (1035)...")
m.connect(0, on_data, preset='1035')

print("Streaming... Press Ctrl+C to exit.")
try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nDisconnecting...")
    m.disconnect()

