
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrated GUI: embebe el backend de streaming (SerialReader) en la GUI de Qt Designer (gui.py)

- ADC en graphicsView_9
- Acelerómetros en graphicsView_10
- Botones Start/Stop -> envían JSON {"cmd":"start"} / {"cmd":"stop"} por el mismo puerto
- Checkboxes:
    * checkBox        -> Acelerómetro 1 (X,Y,Z)
    * checkBox_2      -> Acelerómetro 2 (X,Y,Z)
    * checkBox_3..8   -> ADC CH1..CH6

Notas:
- El firmware debe aceptar comandos JSON con salto de línea, p.ej: {"cmd":"start"}\n
- Este script reutiliza el SerialReader probado en teensy_stream_viewer.py
"""
import argparse
import sys
import os
import json
import csv,queue
import numpy as np
import serial  # pyserial


import time
from datetime import datetime,timedelta
import struct
import threading
from collections import deque

from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg

from gui import Ui_MainWindow            # tu UI exportada desde Qt Designer
#from teensy_stream_viewer import SerialReader  # backend de streaming (ya probado)






# -------------------- CONFIGURACIÓN BÁSICA --------------------
DEFAULT_PORT = "/dev/ttyACM0"   # ajusta si es necesario (Windows: COMx, macOS: /dev/cu.usbmodem*)
DEFAULT_BAUD = 1000000          # ignorado por USB CDC, pero requerido por pyserial
DEFAULT_FS   = 50000.0           # Hz (debe coincidir con SAMPLE_RATE_HZ del firmware)
WINDOW_SECS  = 10.0
POINTS_TARGET = int(WINDOW_SECS * DEFAULT_FS)

RUNNING = 1
IDLE = 0
PAUSED = 2


HEADER = b'\xA5\x5A'
FRAME_SIZE = 38
PAYLOAD_SIZE = FRAME_SIZE - 2  # after header

# Si tus nombres de widgets fueran distintos, cambia aquí:
OBJ_GRAPH_ADC = "graphicsView_11"
OBJ_GRAPH_ACC = "graphicsView_10"
OBJ_BTN_START = "pushButton_36"
OBJ_BTN_STOP  = "pushButton_9"
OBJ_CB_ACC1   = "checkBox"
OBJ_CB_ACC2   = "checkBox_2"
OBJ_CBS_ADC   = ["checkBox_18", "checkBox_19", "checkBox_20", "checkBox_21", "checkBox_22", "checkBox_23"]



# DEFAULT PARAMETERS
EEG_BFC = 0.5
ECG_BFC = 0.05
EMG_BFC = 10

EEG_TFC = 100
ECG_TFC = 150
EMG_TFC = 1000

EEG_GAIN = 1000
ECG_GAIN = 160
EMG_GAIN = 80


MIN_PARAM = 0
MAX_PARAM = 100
MODO_MANUAL = 0
MODO_AUTO   = 1


# --- stacking / offsets ---
STACK_ADC = True
STACK_ACC = True

# offsets en unidades de muestra (ajústalos a tu amplitud típica)
OFFSET_ADC = 12000.0   # p.ej. ±10k -> pon 12000
OFFSET_ACC = 12000.0   # idem para acelerómetros

# escala del canal 24b para verse como 16b (si lo sigues usando en CH1)
#SCALE_ADC24 = 1.0/256.0
SCALE_ADC24 = 1.0/1.0


# --------------------------------------------------------------



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
        self.on_frame = None

        self.lost = 0
        self._last_sid = None
        # Preallocate ring buffers (time and 7 channels)
        self.rate = float(rate)
        self.buf_len = int(buf_seconds * self.rate)
        self.t = np.full(self.buf_len, np.nan, dtype=np.float64)
        self.ch = np.full((12, self.buf_len), np.nan, dtype=np.float32)
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

            payload = self._read_exact(PAYLOAD_SIZE)  # 36 bytes after header
            if len(payload) != PAYLOAD_SIZE:
                continue  # timeout o desalineación

            # -------- Parse --------
            sid = struct.unpack_from('<I', payload, 0)[0]

            # 6 × s24 LE a partir de offset 4 (4..21)
            adc24 = []
            off = 4
            for _ in range(6):
                s = s24_from_le(payload[off+0], payload[off+1], payload[off+2])
                adc24.append(s)
                off += 3

            # 6 × int16 LE en 22..33
            acc = struct.unpack_from('<6h', payload, 22)

            # CRC16-CCITT al final del payload (34..35, big-endian)
            crc_rx = struct.unpack_from('>H', payload, 34)[0]
            if self.verify_crc:
                crc_calc = crc16_ccitt(HEADER + payload[:-2])
                if crc_calc != crc_rx:
                    # frame inválido: NO actualices last_sid ni lost; resincroniza en el próximo header
                    continue

            # -------- Contador de pérdidas --------
            if self._last_sid is not None:
                expected = (self._last_sid + 1) & 0xFFFFFFFF
                if sid != expected:
                    # cuántos frames faltaron (módulo 2^32)
                    self.lost += (sid - expected) & 0xFFFFFFFF

            self._last_sid = sid  # actualizar siempre tras pasar CRC

            # -------- Timestamp y almacenamiento --------
            t = sid / self.rate

            if self.on_frame is not None:
                # 'raw' = trama completa tal como llega (header+payload)
                raw = HEADER + payload
                # Pasa listas simples para que no dependan de NumPy
                try:
                    self.on_frame(sid, t, adc24, acc, raw)
                except Exception:
                    # No derribar el hilo si el callback falla
                    pass

            with self.lock:
                i = self.idx
                self.t[i] = t
                # Guarda los 12 canales: 0..5 = ADC24, 6..11 = ACC
                # Asegúrate que self.ch tenga forma (12, buf_len)
                for k in range(6):
                    self.ch[k,   i] = float(adc24[k])
                    self.ch[k+6, i] = float(acc[k])
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



class App(QtWidgets.QMainWindow):
    def __init__(self, port=DEFAULT_PORT, baud=DEFAULT_BAUD, fs=DEFAULT_FS, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # ---- Localiza los widgets por nombre (por si el .ui cambia) ----
        try:
            self.adc_plot = getattr(self.ui, OBJ_GRAPH_ADC)
            self.acc_plot = getattr(self.ui, OBJ_GRAPH_ACC)
            self.btn_start = getattr(self.ui, OBJ_BTN_START)
            self.btn_stop  = getattr(self.ui, OBJ_BTN_STOP)
            self.cb_acc1 = getattr(self.ui, OBJ_CB_ACC1)
            self.cb_acc2 = getattr(self.ui, OBJ_CB_ACC2)
            self.cb_adc  = [getattr(self.ui, n) for n in OBJ_CBS_ADC]
        except AttributeError as e:
            raise RuntimeError(f"No se encontró un widget esperado en la UI: {e}")


        self.btn_start.setDisabled(False)
        self.btn_stop.setDisabled(True)

        self.state = IDLE
        self.elapsed_time = 0





        self.enable_ch		= [ 0, 0, 0, 0, 0, 0, 0, 0]
        self.bfc 	= [ EEG_BFC, EEG_BFC, EEG_BFC, EEG_BFC, EEG_BFC, EEG_BFC ]
        self.tfc 	= [ EEG_TFC, EEG_TFC, EEG_TFC, EEG_TFC, EEG_TFC, EEG_TFC ]
        self.gain 	= [ EEG_GAIN, EEG_GAIN, EEG_GAIN, EEG_GAIN, EEG_GAIN, EEG_GAIN ]

        self.mode_ch = [ 0, 0, 0, 0, 0, 0] # 0 test; 1 impedance
        self.test_mode_ch = ['EEG','EEG','EEG','EEG','EEG','EEG']


        self.ui.lineEdit_2.isReadOnly()
        self.ui.lineEdit_3.isReadOnly()

        self.enchannels_checks = [	self.ui.checkBox_13,
									self.ui.checkBox_16,
									self.ui.checkBox_14,
									self.ui.checkBox_10,
									self.ui.checkBox_11,
									self.ui.checkBox_9 ]

        self.impedancia_btn = [	self.ui.pushButton_3,
                                self.ui.pushButton_22,
                                self.ui.pushButton_23,
                                self.ui.pushButton_25,
                                self.ui.pushButton_26,
                                self.ui.pushButton_27]

        self.test_btn	= [	self.ui.pushButton_21,
        					self.ui.pushButton_24,
        					self.ui.pushButton_28,
        					self.ui.pushButton_29,
        					self.ui.pushButton_30,
        					self.ui.pushButton_31]

        self.cb_test =[ self.ui.comboBox_9,
        				self.ui.comboBox_12,
        				self.ui.comboBox_11,
        				self.ui.comboBox_10,
        				self.ui.comboBox_8,
        				self.ui.comboBox_13]

        self.set_btns = [	self.ui.pushButton,
        					self.ui.pushButton_2,
        					self.ui.pushButton_4,
        					self.ui.pushButton_6,
        					self.ui.pushButton_17,
        					self.ui.pushButton_18]

        self.sound_btn = [	self.ui.pushButton_14,
        					self.ui.pushButton_13,
        					self.ui.pushButton_12,
        					self.ui.pushButton_11,
        					self.ui.pushButton_10,
        					self.ui.pushButton_15]

        self.bfc_lines = [	self.ui.lineEdit_26,
        					self.ui.lineEdit_35,
        					self.ui.lineEdit_32,
        					self.ui.lineEdit_29,
        					self.ui.lineEdit_23,
        					self.ui.lineEdit_38]

        self.tfc_lines = [	self.ui.lineEdit_27,
        					self.ui.lineEdit_36,
        					self.ui.lineEdit_33,
        					self.ui.lineEdit_30,
        					self.ui.lineEdit_24,
        					self.ui.lineEdit_39]

        self.gain_lines = [	self.ui.lineEdit_28,
        					self.ui.lineEdit_37,
        					self.ui.lineEdit_34,
        					self.ui.lineEdit_31,
        					self.ui.lineEdit_25,
        					self.ui.lineEdit_40]

        for i in range(6):
            self.sound_btn[i].setDisabled(True)
            self.impedancia_btn[i].setDisabled(True)
            self.test_btn[i].setDisabled(True)
            self.cb_test[i].setDisabled(True)
            self.set_btns[i].setDisabled(True)
            #self.bfc_text[i].setDisabled(True)
            #self.tfc_text[i].setDisabled(True)
            #self.gain_text[i].setDisabled(True)
            self.bfc_lines[i].setDisabled(True)
            self.tfc_lines[i].setDisabled(True)
            self.gain_lines[i].setDisabled(True)


        self.ui.pushButton_9.setDisabled(True)
        self.ui.pushButton_35.setDisabled(True)
        self.ui.pushButton_32.setDisabled(True)
        self.ui.pushButton_33.setDisabled(True)
        self.ui.pushButton_34.setDisabled(True)
        self.ui.comboBox_14.setDisabled(True)
        self.ui.lineEdit_41.setDisabled(True)
        self.ui.lineEdit_42.setDisabled(True)
        self.ui.lineEdit_43.setDisabled(True)

        #INITIAL VALUES
        for i in range(6):
            self.bfc_lines[i].setText(str(self.bfc[i]))
            self.tfc_lines[i].setText(str(self.tfc[i]))
            self.gain_lines[i].setText(str(self.gain[i]))
        self.ui.lineEdit_41.setText(str(EEG_BFC))
        self.ui.lineEdit_42.setText(str(EEG_TFC))
        self.ui.lineEdit_43.setText(str(EEG_GAIN))

        # ---- Backend de lectura en hilo ----
        # buffer interno >= ventana; CRC activo para robustez
        self.reader = SerialReader(port, baud, buf_seconds=max(WINDOW_SECS, 60.0), rate=fs, verify_crc=True)
        self.reader.start()

        # ---- Timer para actualizar hora y tiempo transcurrido ----
        #TIME
        self.date_now = QtCore.QDate.currentDate()

        #MGMT OF TIME
        self.clock_timer = QtCore.QTimer()
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self.updateTime)
        self.clock_timer.start()


        # ---- Configura plots ----
        self._setup_plots()

        # ---- Señales/slots ----
        self._connect_signals()


        # --- Estado de logging ---
        self.log_mode = 'bin'      # 'bin' (recomendado) o 'csv'
        self.log_dir = './data'
        self.log_queue = queue.Queue(maxsize=10000)  # cola amplia (frames)
        self.log_thread = None
        self.log_stop = threading.Event()
        self.log_file = None       # handle abierto
        self._run_start_ts = None  # timestamp de inicio de prueba (para nombre de archivo)

        # engancha callback del reader para recibir frames validados (CRC OK)
        self.reader.on_frame = self._on_frame_for_logging


        # ---- Timer GUI ----
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(33)  # ~30 FPS
        self.timer.timeout.connect(self._on_timer)
        self.timer.start()

        self.statusBar().showMessage("Conectando...")

    # ------------------ Plots ------------------
    def _setup_plots(self):
        # ADC (6 curvas)
        self.adc_plot.setLabel('bottom', 'Time', units='s')
        self.adc_plot.showGrid(x=True, y=True, alpha=0.3)
        self.adc_plot.addLegend()
        self.adc_names = [f"CH{i+1}" for i in range(6)]
        self.adc_curves = [self.adc_plot.plot(name=f"CH{i+1}") for i in range(6)]

        # ACC (6 curvas: A1 xyz, A2 xyz)
        self.acc_plot.setLabel('bottom', 'Time', units='s')
        self.acc_plot.showGrid(x=True, y=True, alpha=0.3)
        self.acc_plot.addLegend()
        self.acc_names = ["A1-X", "A1-Y", "A1-Z", "A2-X", "A2-Y", "A2-Z"]
        self.acc_curves = [self.acc_plot.plot(name=nm) for nm in self.acc_names]




    # --------------- Conexión señales ---------------
    def _connect_signals(self):
        # Botones Start/Stop -> JSON
        self.btn_start.clicked.connect(self.startSample)
        self.btn_stop.clicked.connect(self.stopSample)

        # Checkboxes
        self.cb_acc1.stateChanged.connect(self._update_visibility)
        self.cb_acc2.stateChanged.connect(self._update_visibility)
        for cb in self.cb_adc:
            cb.stateChanged.connect(self._update_visibility)

        self.enchannels_checks[0].stateChanged.connect(lambda:self.enableChannel(0))
        self.enchannels_checks[1].stateChanged.connect(lambda:self.enableChannel(1))
        self.enchannels_checks[2].stateChanged.connect(lambda:self.enableChannel(2))
        self.enchannels_checks[3].stateChanged.connect(lambda:self.enableChannel(3))
        self.enchannels_checks[4].stateChanged.connect(lambda:self.enableChannel(4))
        self.enchannels_checks[5].stateChanged.connect(lambda:self.enableChannel(5))

        self.ui.checkBox_12.stateChanged.connect(lambda:self.enableAltChannel(6))
        self.ui.checkBox_15.stateChanged.connect(lambda:self.enableAltChannel(7))
        self.ui.checkBox_17.stateChanged.connect(self.enableAllChannel)

        #SET IMPEDANCE MODE
        self.impedancia_btn[0].clicked.connect(lambda:self.impedanceMode(0))
        self.impedancia_btn[1].clicked.connect(lambda:self.impedanceMode(1))
        self.impedancia_btn[2].clicked.connect(lambda:self.impedanceMode(2))
        self.impedancia_btn[3].clicked.connect(lambda:self.impedanceMode(3))
        self.impedancia_btn[4].clicked.connect(lambda:self.impedanceMode(4))
        self.impedancia_btn[5].clicked.connect(lambda:self.impedanceMode(5))
        self.ui.pushButton_32.clicked.connect(self.impedanceMasterMode)

        #SET TEST MODE
        self.test_btn[0].clicked.connect(lambda:self.testMode(0))
        self.test_btn[1].clicked.connect(lambda:self.testMode(1))
        self.test_btn[2].clicked.connect(lambda:self.testMode(2))
        self.test_btn[3].clicked.connect(lambda:self.testMode(3))
        self.test_btn[4].clicked.connect(lambda:self.testMode(4))
        self.test_btn[5].clicked.connect(lambda:self.testMode(5))
        self.ui.pushButton_33.clicked.connect(self.testMasterMode)

        #SELECT TEST TYPE
        self.cb_test[0].currentIndexChanged.connect(lambda:self.changeType(0))
        self.cb_test[1].currentIndexChanged.connect(lambda:self.changeType(1))
        self.cb_test[2].currentIndexChanged.connect(lambda:self.changeType(2))
        self.cb_test[3].currentIndexChanged.connect(lambda:self.changeType(3))
        self.cb_test[4].currentIndexChanged.connect(lambda:self.changeType(4))
        self.cb_test[5].currentIndexChanged.connect(lambda:self.changeType(5))
        self.ui.comboBox_14.currentIndexChanged.connect(self.changeMasterType)

        #SET PARAMETERS
        self.set_btns[0].clicked.connect(lambda:self.setParameters(0))
        self.set_btns[1].clicked.connect(lambda:self.setParameters(1))
        self.set_btns[2].clicked.connect(lambda:self.setParameters(2))
        self.set_btns[3].clicked.connect(lambda:self.setParameters(3))
        self.set_btns[4].clicked.connect(lambda:self.setParameters(4))
        self.set_btns[5].clicked.connect(lambda:self.setParameters(5))



        # Estado inicial: todo visible
        self.cb_acc1.setChecked(True)
        self.cb_acc2.setChecked(True)
        for cb in self.cb_adc:
            cb.setChecked(True)
        self._update_visibility()

    def _update_visibility(self):
        # Accelerometer groups
        acc1_on = self.cb_acc1.isChecked()
        acc2_on = self.cb_acc2.isChecked()
        for i in range(3):      # A1 xyz
            self.acc_curves[i].setVisible(acc1_on)
        for i in range(3, 6):   # A2 xyz
            self.acc_curves[i].setVisible(acc2_on)

        # ADC CH1..CH6
        for i, cb in enumerate(self.cb_adc):
            self.adc_curves[i].setVisible(cb.isChecked())



	# --------------- logged functions ------------
    def _timestamp_for_filename(self):
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def _ensure_log_dir(self):
        os.makedirs(self.log_dir, exist_ok=True)

    def _open_log_file(self):
        self._ensure_log_dir()
        ts = self._timestamp_for_filename()
        self._run_start_ts = ts
        if self.log_mode == 'bin':
            path = os.path.join(self.log_dir, f"{ts}.bin")
            self.log_file = open(path, "wb", buffering=1024*1024)  # buffer grande
            self.statusBar().showMessage(f"Logging BIN → {path}")
        else:
            path = os.path.join(self.log_dir, f"{ts}.csv")
            self.log_file = open(path, "w", newline='', buffering=1024*1024)
            self._csv_writer = csv.writer(self.log_file)
            # cabecera CSV
            self._csv_writer.writerow(
                ["sid","t","adc1","adc2","adc3","adc4","adc5","adc6","ax1","ay1","az1","ax2","ay2","az2"]
            )
            self.statusBar().showMessage(f"Logging CSV → {path}")

    def _close_log_file(self):
        try:
            if self.log_file:
                self.log_file.flush()
                self.log_file.close()
        except Exception:
            pass
        self.log_file = None

    def _log_worker(self):
        """Hilo escritor: drena la cola y escribe en disco."""
        try:
            while not self.log_stop.is_set():
                try:
                    item = self.log_queue.get(timeout=0.2)  # (mode, data)
                except queue.Empty:
                    continue

                mode, data = item
                if mode == 'bin':
                    # data = raw bytes
                    self.log_file.write(data)
                elif mode == 'csv':
                    # data = tuple(sid, t, adc6, acc6)
                    sid, tt, adc6, acc6 = data
                    self._csv_writer.writerow([sid, f"{tt:.9f}"] + list(adc6) + list(acc6))
                # permitir que el SO vacíe buffers sin bloquear hilo de GUI
                # (flushea cada tanto; no en cada línea)
        except Exception as e:
            # no reventar la app por error del logger
            pass

    def _start_logging(self):
        """Abrir archivo y lanzar hilo escritor."""
        self.log_stop.clear()
        self._open_log_file()
        self.log_thread = threading.Thread(target=self._log_worker, daemon=True)
        self.log_thread.start()

    def _stop_logging(self):
        """Cerrar hilo y archivo."""
        self.log_stop.set()
        # vaciar cola pendiente
        while not self.log_queue.empty():
            try:
                item = self.log_queue.get_nowait()
                mode, data = item
                if mode == 'bin':
                    self.log_file.write(data)
                else:
                    sid, tt, adc6, acc6 = data
                    self._csv_writer.writerow([sid, f"{tt:.9f}"] + list(adc6) + list(acc6))
            except Exception:
                break
        self._close_log_file()
        self.log_thread = None

    def _on_frame_for_logging(self, sid, t, adc24_list, acc_list, raw_bytes):
        """
        Callback invocada desde el hilo lector (reader).
        Encola datos para que el hilo escritor los procese (no bloquear el lector).
        """
        if self.state != RUNNING:
            return
        try:
            if self.log_mode == 'bin':
                # guardar tal cual llega (header+payload)
                self.log_queue.put_nowait(('bin', raw_bytes))
            else:
                # CSV: guardar valores parseados
                # adc24_list: 6 enteros (24-bit en int32), acc_list: 6 int16
                self.log_queue.put_nowait(('csv', (sid, t, tuple(adc24_list), tuple(acc_list))))
        except queue.Full:
            # En caso extremo de que la cola se llene, descartamos (para no frenar la adquisición)
            pass

    def _clear_reader_buffers_and_plots(self):
        """Resetear ring buffer y limpiar plots al iniciar una prueba."""
        # 1) Reset de buffers del reader
        with self.reader.lock:
            self.reader.idx = 0
            self.reader.wraps = 0
            self.reader.lost = 0
            self.reader._last_sid = None
            self.reader.t[:] = np.nan
            self.reader.ch[:] = np.nan
        # 2) Limpiar las curvas
        for c in self.adc_curves:
            c.setData([], [])
        for c in self.acc_curves:
            c.setData([], [])



    # --------------- Used functions ---------------

    def updateTime(self):
        if self.state == RUNNING:
            self.elapsed_time += 1
            self.ui.lineEdit_3.setText(str(timedelta(seconds = self.elapsed_time)))
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        self.ui.lineEdit_2.setText(current_time)

    def startSample(self):
        self._clear_reader_buffers_and_plots()

        self.log_mod = 'bin'
        self._start_logging()

        self.send_cmd({"cmd": "start"})
        self.state = RUNNING
        self.btn_start.setDisabled(True)
        self.btn_stop.setDisabled(False)
        self.statusBar().showMessage("RUNNING + logging...")

    def stopSample(self):
        self.send_cmd({"cmd": "stop"})
        self.state = IDLE
        self.btn_start.setDisabled(False)
        self.btn_stop.setDisabled(True)
        self._stop_logging()
        self.statusBar().showMessage("STOPPED; logging saved.")

    def enableChannel(self, _ch):
        if self.enchannels_checks[_ch].isChecked():
            print("canal {} habilitado".format(_ch+1))
            self.enable_ch[_ch] = 1
            self.sound_btn[_ch].setDisabled(False)
            if self.mode_ch[_ch] == 0: #test mode
                print("test mode")
                self.impedancia_btn[_ch].setDisabled(False)
                self.sound_btn[_ch].setDisabled(False)
                self.test_btn[_ch].setDisabled(True)
            elif self.mode_ch[_ch] == 1: #impedance mode
                print("impedance mode")
                self.impedancia_btn[_ch].setDisabled(True)
                self.test_btn[_ch].setDisabled(False)
                self.sound_btn[_ch].setDisabled(False)
            else:	# sound mode
                self.impedancia_btn[_ch].setDisabled(False)
                self.test_btn[_ch].setDisabled(False)
                self.sound_btn[_ch].setDisabled(True)
            self.cb_test[_ch].setDisabled(False)
            self.set_btns[_ch].setDisabled(False)
            self.sound_btn[_ch].setDisabled(False)
            #self.bfc_text[_ch].setDisabled(False)
            #self.tfc_text[_ch].setDisabled(False)
            #self.gain_text[_ch].setDisabled(False)
            self.bfc_lines[_ch].setDisabled(False)
            self.tfc_lines[_ch].setDisabled(False)
            self.gain_lines[_ch].setDisabled(False)
        else:
            print("canal {} deshabilitado".format(_ch))
            self.enable_ch[_ch] = 0
            self.impedancia_btn[_ch].setDisabled(True)
            self.test_btn[_ch].setDisabled(True)
            self.cb_test[_ch].setDisabled(True)
            self.set_btns[_ch].setDisabled(True)
            self.sound_btn[_ch].setDisabled(True)
            #self.bfc_text[_ch].setDisabled(True)
            #self.tfc_text[_ch].setDisabled(True)
            #self.gain_text[_ch].setDisabled(True)
            self.bfc_lines[_ch].setDisabled(True)
            self.tfc_lines[_ch].setDisabled(True)
            self.gain_lines[_ch].setDisabled(True)

    def enableAltChannel(self,_ch):
        pass

    def enableAllChannel(self):
        if self.ui.checkBox_17.isChecked():
            self.ui.pushButton_35.setDisabled(False)
            self.ui.pushButton_32.setDisabled(False)
            self.ui.pushButton_33.setDisabled(True)
            self.ui.pushButton_34.setDisabled(False)
            self.ui.comboBox_14.setDisabled(False)
            self.ui.lineEdit_41.setDisabled(False)
            self.ui.lineEdit_42.setDisabled(False)
            self.ui.lineEdit_43.setDisabled(False)

            for _ch in range(6):
                print("canal {} habilitado".format(_ch+1))
                self.enchannels_checks[_ch].setChecked(True)
                self.enable_ch[_ch] = 1
                self.sound_btn[_ch].setDisabled(False)
                if self.mode_ch[_ch] == 0:
                    self.impedancia_btn[_ch].setDisabled(False)
                    self.sound_btn[_ch].setDisabled(False)
                    self.test_btn[_ch].setDisabled(True)
                elif self.mode_ch[_ch] == 1:
                    self.impedancia_btn[_ch].setDisabled(True)
                    self.test_btn[_ch].setDisabled(False)
                    self.sound_btn[_ch].setDisabled(False)
                else:
                    self.impedancia_btn[_ch].setDisabled(False)
                    self.test_btn[_ch].setDisabled(False)
                    self.sound_btn[_ch].setDisabled(True)
                self.cb_test[_ch].setDisabled(False)
                self.set_btns[_ch].setDisabled(False)
                #self.bfc_text[_ch].setDisabled(False)
                #self.tfc_text[_ch].setDisabled(False)
                #self.gain_text[_ch].setDisabled(False)
                self.bfc_lines[_ch].setDisabled(False)
                self.tfc_lines[_ch].setDisabled(False)
                self.gain_lines[_ch].setDisabled(False)
        else:
            self.ui.pushButton_35.setDisabled(True)
            self.ui.pushButton_32.setDisabled(True)
            self.ui.pushButton_33.setDisabled(True)
            self.ui.pushButton_34.setDisabled(True)
            self.ui.comboBox_14.setDisabled(True)
            self.ui.lineEdit_41.setDisabled(True)
            self.ui.lineEdit_42.setDisabled(True)
            self.ui.lineEdit_43.setDisabled(True)

            for _ch in range(6):
                print("canal {} deshabilitado".format(_ch))
                self.enable_ch[_ch] = 0
                self.enchannels_checks[_ch].setChecked(False)
                self.impedancia_btn[_ch].setDisabled(True)
                self.test_btn[_ch].setDisabled(True)
                self.cb_test[_ch].setDisabled(True)
                self.set_btns[_ch].setDisabled(True)
                self.sound_btn[_ch].setDisabled(True)
                #self.bfc_text[_ch].setDisabled(True)
                #self.tfc_text[_ch].setDisabled(True)
                #self.gain_text[_ch].setDisabled(True)
                self.bfc_lines[_ch].setDisabled(True)
                self.tfc_lines[_ch].setDisabled(True)
                self.gain_lines[_ch].setDisabled(True)

    def impedanceMode(self,_ch ):
        self.mode_ch[_ch] = 1
        self.impedancia_btn[_ch].setDisabled(True)
        self.test_btn[_ch].setDisabled(False)
        self.sound_btn[_ch].setDisabled(False)

    def impedanceMasterMode(self):
        self.ui.pushButton_33.setDisabled(False)
        self.ui.pushButton_32.setDisabled(True)
        for i in range(6):
            self.impedanceMode(i)

    def testMode(self,_ch ):
        self.mode_ch[_ch] = 0
        self.impedancia_btn[_ch].setDisabled(False)
        self.test_btn[_ch].setDisabled(True)
        self.sound_btn[_ch].setDisabled(False)

    def testMasterMode(self):
        self.ui.pushButton_33.setDisabled(True)
        self.ui.pushButton_32.setDisabled(False)
        for i in range(6):
            self.testMode(i)

    def soundMode(self,_ch ):
        self.mode_ch[_ch] = 2
        self.impedancia_btn[_ch].setDisabled(False)
        self.test_btn[_ch].setDisabled(False)
        self.sound_btn[_ch].setDisabled(False)

    def changeType(self,_ch):
        mode = self.cb_test[_ch].currentText()
        #print(mode)
        if mode == "EEG":
            self.bfc[_ch] 	= EEG_BFC
            self.tfc[_ch] 	= EEG_TFC
            self.gain[_ch] 	= EEG_GAIN
            self.bfc_lines[_ch].setText(str(EEG_BFC))
            self.tfc_lines[_ch].setText(str(EEG_TFC))
            self.gain_lines[_ch].setText(str(EEG_GAIN))
        elif mode == "EMG":
            self.bfc[_ch] 	= EMG_BFC
            self.tfc[_ch] 	= EMG_TFC
            self.gain[_ch] 	= EMG_GAIN
            self.bfc_lines[_ch].setText(str(EMG_BFC))
            self.tfc_lines[_ch].setText(str(EMG_TFC))
            self.gain_lines[_ch].setText(str(EMG_GAIN))
        elif mode == "ECG":
            self.bfc[_ch] 	= ECG_BFC
            self.tfc[_ch] 	= ECG_TFC
            self.gain[_ch] 	= ECG_GAIN
            self.bfc_lines[_ch].setText(str(ECG_BFC))
            self.tfc_lines[_ch].setText(str(ECG_TFC))
            self.gain_lines[_ch].setText(str(ECG_GAIN))

        self.test_mode_ch[_ch] = mode

    def changeMasterType(self):
        mode  = self.ui.comboBox_14.currentText()
        if mode == "EEG":
            self.ui.lineEdit_41.setText(str(EEG_BFC))
            self.ui.lineEdit_42.setText(str(EEG_TFC))
            self.ui.lineEdit_43.setText(str(EEG_GAIN))
            for i in range(6):
                self.cb_test[i].setCurrentText("EEG")
                self.changeType(i)
        elif mode == "EMG":
            self.ui.lineEdit_41.setText(str(EMG_BFC))
            self.ui.lineEdit_42.setText(str(EMG_TFC))
            self.ui.lineEdit_43.setText(str(EMG_GAIN))
            for i in range(6):
                self.cb_test[i].setCurrentText("EMG")
                self.changeType(i)
        elif mode == "ECG":
            self.ui.lineEdit_41.setText(str(ECG_BFC))
            self.ui.lineEdit_42.setText(str(ECG_TFC))
            self.ui.lineEdit_43.setText(str(ECG_GAIN))
            for i in range(6):
                self.cb_test[i].setCurrentText("ECG")
                self.changeType(i)
        elif mode == "Manual":
            for i in range(6):
                self.cb_test[i].setCurrentText("Manual")
                self.changeType(i)




    # --------------- Comandos JSON a firmware ---------------
    def send_cmd(self, obj):
        """
        Envía un JSON en una línea (terminado en '\n') al mismo puerto serie del stream.
        Requiere que el firmware lea la línea y ejecute el comando.
        """
        try:
            ser = self.reader._ser   # acceso directo al Serial del hilo
            if ser is None or not self.reader.connected.is_set():
                self.statusBar().showMessage("No conectado")
                return
            line = (json.dumps(obj) + "\n").encode('utf-8')
            # evitar bloqueos largos
            if ser.out_waiting < 4096:
                ser.write(line)
                self.statusBar().showMessage(f"Enviado: {obj}")
            else:
                self.statusBar().showMessage("Tx saturado, intente de nuevo")
        except Exception as e:
            self.statusBar().showMessage(f"Error al enviar comando: {e}")

    # --------------- Actualización periódica de plots ---------------
    def _stack_rows(self, Y: np.ndarray, offset: float) -> np.ndarray:
        """
        Devuelve una copia apilada: fila i -> y[i] + i*offset
        """
        if not offset:
            return Y
        Z = Y.copy()
        rows = Z.shape[0]
        for i in range(rows):
            Z[i, :] += i * float(offset)
        return Z

    def _set_axis_ticks(self, plot_widget, offset: float, names: list):
        """
        Coloca etiquetas en el eje Y en los niveles i*offset.
        Aunque un canal esté oculto, mantenemos su tick para evitar saltos.
        """
        ax = plot_widget.getAxis('left')
        if not offset:
            # sin offset: no forcemos ticks personalizados
            ax.setTicks(None)
            return
        ticks = [(i*float(offset), names[i]) for i in range(len(names))]
        # setTicks recibe una lista de “niveles”; pasamos uno
        ax.setTicks([ticks])


    def _on_timer(self):

        #update time
        snap = self.reader.get_snapshot()
        if snap[0] is None:
            return
        t, ch = snap
        if t.size < 2:
            return

        # recorte a ventana visible
        t_end = t[-1]
        t_start = max(0.0, t_end - WINDOW_SECS)
        i0 = np.searchsorted(t, t_start, side='left')
        t_win = t[i0:]
        y_win = ch[:, i0:]      # ch[0]=ADC24 (sintético por ahora), ch[1:]=6 ejes ACC


        # decimación simple para rendimiento
        N = t_win.size
        px = max(800, self.adc_plot.width())
        target = max(2*px, int(self.reader.rate))   # suficiente densidad para 1 kHz
        step = max(1, N // target)
        t_d = t_win[::step]
        y_d = y_win[:, ::step]


        # ----- ACC: 6 filas (6..11) -----
        acc_raw = y_d[6:12, :]
        acc_plot = self._stack_rows(acc_raw, OFFSET_ACC) if STACK_ACC else acc_raw
        self._set_axis_ticks(self.acc_plot, OFFSET_ACC if STACK_ACC else 0.0, self.acc_names)
        for i in range(6):
            self.acc_curves[i].setData(t_d, acc_plot[i, :], _callSync='off')

        # ----- ADC: 6 filas (0..5) -----
        adc_raw = y_d[0:6, :] * float(SCALE_ADC24)
        adc_plot = self._stack_rows(adc_raw, OFFSET_ADC) if STACK_ADC else adc_raw
        self._set_axis_ticks(self.adc_plot, OFFSET_ADC if STACK_ADC else 0.0, self.adc_names)
        for i in range(6):
            self.adc_curves[i].setData(t_d, adc_plot[i, :], _callSync='off')

        # # ----- Acelerómetros: ch[1:4] A1 xyz, ch[4:7] A2 xyz -----
        # for i in range(3):
        #     self.acc_curves[i].setData(t_d, y_d[i+1, :], _callSync='off')
        # for i in range(3):
        #     self.acc_curves[i+3].setData(t_d, y_d[i+4, :], _callSync='off')

        # ----- ADC: hoy sólo tenemos un canal sintético de 24 b en ch[0] -----
        # Escalar 24 b a ~16 b para vista
        #adc0 = y_d[0, :] * (1.0/1.0)
        #self.adc_curves[0].setData(t_d, adc0, _callSync='off')

        # CH2..CH6 quedan listos para mapear ADS1299 reales cuando estén:
        # self.adc_curves[1].setData(t_d, adc_ch2, ...)
        # ...

        # estado
        self.statusBar().showMessage(
            f"samples={N}  fs={self.reader.rate:.0f} Hz  lost={self.reader.lost}"
        )




    def closeEvent(self, ev):
        try:
            self.reader.stop()
        except Exception:
            pass
        super().closeEvent(ev)


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = App(port=DEFAULT_PORT, baud=DEFAULT_BAUD, fs=DEFAULT_FS)
    w.resize(1200, 800)
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
