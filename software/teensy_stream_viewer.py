#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teensy 4.1 USB-CDC real-time viewer for extended frame (23 bytes):
[0xA5,0x5A] + u32 sample_id + s24 adc + 6×int16 + CRC16-CCITT (big-endian)
Author: ChatGPT + Wladimir
"""

import argparse
import sys
import time
import struct
import threading
from collections import deque

import numpy as np

try:
    import serial  # pyserial
except Exception as e:
    print("ERROR: pyserial is required. Install with: pip install pyserial", file=sys.stderr)
    raise

# GUI / plotting
try:
    from PyQt5 import QtWidgets, QtCore
    import pyqtgraph as pg
except Exception as e:
    print("ERROR: PyQt5 and pyqtgraph are required. Install with: pip install PyQt5 pyqtgraph", file=sys.stderr)
    raise


HEADER = b'\xA5\x5A'
FRAME_SIZE = 23
PAYLOAD_SIZE = FRAME_SIZE - 2  # after header

def crc16_ccitt(data: bytes, init=0xFFFF) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)"""
    crc = init
    for b in data:
        crc ^= (b << 8) & 0xFFFF
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def s24_from_le(b0, b1, b2) -> int:
    """Convert 3 little-endian bytes to signed 24-bit integer."""
    u = b0 | (b1 << 8) | (b2 << 16)
    if u & 0x800000:
        u -= 0x1000000
    return int(u)


class SerialReader(threading.Thread):
    """Background reader that parses frames and pushes them to a ring buffer."""
    def __init__(self, port: str, baud: int, buf_seconds: float, rate: float, verify_crc: bool=True):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.verify_crc = verify_crc
        self.stop_flag = threading.Event()
        self.connected = threading.Event()
        self.lost = 0
        self._last_sid = None
        # Preallocate ring buffers (time and 7 channels)
        self.rate = float(rate)
        self.buf_len = int(buf_seconds * self.rate)
        self.t = np.full(self.buf_len, np.nan, dtype=np.float64)
        self.ch = np.full((7, self.buf_len), np.nan, dtype=np.float32)
        self.idx = 0
        self.wraps = 0
        self.lock = threading.Lock()

        self._ser = None
        self._last_sid = None

    def run(self):
        while not self.stop_flag.is_set():
            try:
                self._open()
                self._read_loop()
            except Exception as e:
                # Connection dropped or parse error; attempt reconnect after short delay
                self.connected.clear()
                try:
                    if self._ser:
                        self._ser.close()
                except Exception:
                    pass
                time.sleep(0.5)

    def _open(self):
        self._ser = serial.Serial(self.port, self.baud, timeout=1)
        # For USB CDC, baud is ignored; ok.
        self.connected.set()
        print(f"[OK] Connected to {self.port}")

    def _sync_to_header(self):
        """Find header 0xA5 0x5A in the stream."""
        ser = self._ser
        # Read bytes until we see 0xA5 0x5A
        while not self.stop_flag.is_set():
            b = ser.read(1)
            if not b:
                continue
            if b == b'\xA5':
                b2 = ser.read(1)
                if b2 == b'\x5A':
                    return True
        return False

    def _read_exact(self, n: int) -> bytes:
        ser = self._ser
        buf = bytearray()
        while len(buf) < n and not self.stop_flag.is_set():
            chunk = ser.read(n - len(buf))
            if not chunk:
                break
            buf.extend(chunk)
        return bytes(buf)

    def _read_loop(self):
        ser = self._ser
        while not self.stop_flag.is_set():
            if not self._sync_to_header():
                break
            # Read 21 bytes of payload after header
            payload = self._read_exact(PAYLOAD_SIZE)
            if len(payload) != PAYLOAD_SIZE:
                # Lost sync or timeout; restart sync
                continue

            # Parse fields
            sid = struct.unpack_from('<I', payload, 0)[0]
            # s24 little-endian at offset 4..6
            s24 = s24_from_le(payload[4], payload[5], payload[6])
            acc = struct.unpack_from('<6h', payload, 7)  # int16 * 6
            crc_rx = struct.unpack_from('>H', payload, 19)[0]  # big-endian at last two bytes

            if self._last_sid is not None and sid != (self._last_sid + 1) % (1<<32):
                self.lost += (sid - self._last_sid - 1) % (1<<32)
                self._last_sid = sid

            if self.verify_crc:
                crc_calc = crc16_ccitt(HEADER + payload[:-2])
                if crc_calc != crc_rx:
                    # Bad CRC: drop and resync
                    continue

            # Build timestamps from sample_id to keep perfect time base
            t = sid / self.rate

            # Store into ring buffer
            with self.lock:
                i = self.idx
                self.t[i] = t
                # channels: 0 = s24, 1..6 = acc
                self.ch[0, i] = float(s24)  # raw units
                for k in range(6):
                    self.ch[k+1, i] = float(acc[k])
                self.idx = (i + 1) % self.buf_len
                if self.idx == 0:
                    self.wraps += 1

    def get_snapshot(self):
        """Return a chronological snapshot: time and 7×N data, already ordered."""
        with self.lock:
            n = self.buf_len if self.wraps > 0 else self.idx
            if n == 0:
                return None, None
            if self.wraps == 0:
                t = self.t[:n].copy()
                ch = self.ch[:, :n].copy()
            else:
                # reassemble from ring
                i = self.idx
                t = np.concatenate([self.t[i:], self.t[:i]])
                ch = np.concatenate([self.ch[:, i:], self.ch[:, :i]], axis=1)
        return t, ch

    def stop(self):
        self.stop_flag.set()
        try:
            if self._ser:
                self._ser.close()
        except Exception:
            pass


class Viewer(QtWidgets.QMainWindow):
    def __init__(self, reader: SerialReader, window_secs: float, downsample_target_pts: int = 3000):
        super().__init__()
        self.reader = reader
        self.window_secs = window_secs
        self.downsample_target_pts = max(500, int(downsample_target_pts))
        self.no_decimate = False


        self.setWindowTitle("Teensy Realtime Viewer (USB CDC, 7 ch)")

        cw = QtWidgets.QWidget()
        self.setCentralWidget(cw)
        layout = QtWidgets.QVBoxLayout(cw)

        # Plot widget
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel('bottom', 'Time', units='s')
        self.plot.setClipToView(True)
        layout.addWidget(self.plot, 1)

        # Curves
        colors = [pg.intColor(i, hues=7) for i in range(7)]
        names = ["ADC24", "AX1", "AY1", "AZ1", "AX2", "AY2", "AZ2"]
        self.curves = []
        for i in range(7):
            c = self.plot.plot(pen=colors[i], name=names[i])
            self.curves.append(c)

        # Legend
        self.plot.addLegend()

        # Status bar
        self.status = self.statusBar()
        self.last_sid = None
        self.last_update_t = time.time()

        # Timer
        self.timer = QtCore.QTimer()
        self.timer.setInterval(33)  # ~30 FPS
        self.timer.timeout.connect(self.on_timer)
        self.timer.start()

        # scaling for channel 0 (ADC24)
        self.scale0 = 1.0/256.0

        # Shortcuts
        QtWidgets.QShortcut(QtCore.Qt.Key_S, self, self.save_csv)
        QtWidgets.QShortcut(QtCore.Qt.Key_Q, self, self.close)

        # CSV buffer (optional)
        self.csv_buf = deque(maxlen=500000)  # cap CSV rows stored (~5e5)

        # Info
        #self.status.showMessage("Press 'S' to save CSV of current window. Press 'Q' to quit.")



    def on_timer(self):
        snap = self.reader.get_snapshot()
        # snap is a (t, ch) tuple. If empty, t is None.
        if snap[0] is None:
            return
        t, ch = snap

        # Limit to last window
        t_end = t[-1]
        t_start = max(0.0, t_end - self.window_secs)
        # Find index where t >= t_start
        i0 = np.searchsorted(t, t_start, side='left')
        t_win = t[i0:]
        y_win = ch[:, i0:]  # shape (7, N)

        if t_win.size < 2:
            return

        # Adaptive decimation to keep plots responsive
        N = t_win.size
        if self.no_decimate:
            step = 1
        else:
            step = max(1, N // self.downsample_target_pts)
        t_dec = t_win[::step]
        y_dec = y_win[:, ::step]

        # Apply scaling for ch0 (ADC24) to bring to ~16-bit range if desired
        y_dec[0, :] = y_dec[0, :] * float(self.scale0)
        # Update each curve
        for k, curve in enumerate(self.curves):
            curve.setData(t_dec, y_dec[k, :], _callSync='off')

        # update status
        now = time.time()
        if now - self.last_update_t > 0.5:
            self.status.showMessage(f"samples={N}  fs={self.reader.rate:.0f} Hz  window={self.window_secs:.1f}s  step={step}  t=[{t_start:.3f},{t_end:.3f}]")
            self.status.showMessage(f"samples={N}  fs={self.reader.rate:.0f} Hz  lost={self.reader.lost}  ...")
            self.last_update_t = now

        # For optional CSV save (keep only current window)
        self.csv_buf.clear()
        # stack: sid (derived), adc24, 6 acc
        # derive sample_id approx from time * rate
        sid_base = int(t_start * self.reader.rate)
        for j in range(t_dec.size):
            row = [int(round(t_dec[j] * self.reader.rate))] + [float(y_dec[k, j]) for k in range(7)]
            self.csv_buf.append(row)

    def save_csv(self):
        # Save visible decimated data to CSV
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save CSV", "teensy_stream.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            import csv
            with open(path, 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(["sample_id", "adc24", "ax1", "ay1", "az1", "ax2", "ay2", "az2"])
                for row in self.csv_buf:
                    w.writerow(row)
            self.status.showMessage(f"Saved CSV: {path}")
        except Exception as e:
            self.status.showMessage(f"Error saving CSV: {e}")

    def closeEvent(self, event):
        self.reader.stop()
        super().closeEvent(event)


def main():
    ap = argparse.ArgumentParser(description="Teensy 4.1 USB CDC realtime viewer (extended frame 23B)")
    ap.add_argument("--port", default="/dev/ttyACM0", help="Serial port (e.g., /dev/ttyACM0, COM5)")
    ap.add_argument("--baud", type=int, default=1000000, help="Baud rate (ignored for USB CDC, but needed by pyserial)")
    ap.add_argument("--window", type=float, default=10.0, help="Window length in seconds to display")
    ap.add_argument("--buffer", type=float, default=60.0, help="Internal ring buffer seconds (>= window)")
    ap.add_argument("--rate", type=float, default=5000.0, help="Sample rate used to derive time from sample_id")
    ap.add_argument("--nocrc", action="store_true", help="Disable CRC verification")
    ap.add_argument("--scale0", type=float, default=1.0/1.0,
                    help="Multiply factor for channel 0 (ADC24). Default 1/256 to match ~16-bit range.")
    ap.add_argument("--points", type=int, default=3000,
                    help="Approx. points per trace after decimation. Set large (e.g., 50000) to see every sample.")
    ap.add_argument("--no-decimate", action="store_true",
                    help="Disable decimation entirely (may be heavy for large windows).")
    args = ap.parse_args()

    if args.buffer < args.window:
        print("ERROR: --buffer debe ser >= --window", file=sys.stderr)
        return 1

    reader = SerialReader(args.port, args.baud, buf_seconds=args.buffer, rate=args.rate, verify_crc=not args.nocrc)
    reader.start()

    app = QtWidgets.QApplication([])
    viewer = Viewer(reader, window_secs=args.window, downsample_target_pts=args.points)
    viewer.scale0 = float(args.scale0)
    viewer.no_decimate = bool(args.no_decimate)
    viewer.resize(1200, 700)
    viewer.show()
    rc = app.exec_()
    reader.stop()
    return rc


if __name__ == "__main__":
    sys.exit(main())
