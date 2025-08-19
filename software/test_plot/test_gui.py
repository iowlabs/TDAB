import sys
import struct
import threading
from collections import deque
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout
from PyQt5.QtCore import QTimer

import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

import serial

# Configuración
SERIAL_PORT = '/dev/ttyACM0'
BAUD_RATE = 1000000
SAMPLES_PER_FRAME = 500
SAMPLE_INTERVAL_MS = 0.2
NUM_CHANNELS = 6

class SerialPlotter(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Adquisición desde Teensy")
        self.running = False

        # Buffers
        self.buffers = [deque([0]*SAMPLES_PER_FRAME, maxlen=SAMPLES_PER_FRAME) for _ in range(NUM_CHANNELS)]
        self.time_buffer = deque([i*SAMPLE_INTERVAL_MS for i in range(SAMPLES_PER_FRAME)], maxlen=SAMPLES_PER_FRAME)

        # Serial
        self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        self.lock = threading.Lock()

        # UI
        self.init_ui()

        # Timer de refresco gráfico
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(50)

        # Hilo de lectura serial
        self.reader_thread = threading.Thread(target=self.serial_reader, daemon=True)
        self.reader_thread.start()

    def init_ui(self):
        layout = QVBoxLayout()

        # Canvas matplotlib
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, sharex=True, figsize=(8, 5))
        self.canvas = FigureCanvas(self.fig)

        # Inicializar líneas
        self.lines1 = []
        self.lines2 = []
        self.colors = ['b', 'g', 'r', 'c', 'm', 'y']
        for i in range(3):
            line, = self.ax1.plot(self.time_buffer, self.buffers[i], color=self.colors[i], label=f'ch{i+1}')
            self.lines1.append(line)
        for i in range(3, 6):
            line, = self.ax2.plot(self.time_buffer, self.buffers[i], color=self.colors[i], label=f'ch{i+1}')
            self.lines2.append(line)

        self.ax1.set_ylabel("EEG signals")
        self.ax2.set_ylabel("IMU signals")
        self.ax2.set_xlabel("Tiempo (ms)")
        self.ax1.legend()
        self.ax2.legend()
        self.ax1.set_ylim(-1200, 1200)
        self.ax2.set_ylim(-1200, 1200)

        layout.addWidget(self.canvas)

        # Botones
        self.btn_start = QPushButton("Iniciar adquisición")
        self.btn_start.clicked.connect(self.start_acquisition)
        layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Detener adquisición")
        self.btn_stop.clicked.connect(self.stop_acquisition)
        layout.addWidget(self.btn_stop)

        self.setLayout(layout)

    def start_acquisition(self):
        self.running = True
        print("Adquisición iniciada")

    def stop_acquisition(self):
        self.running = False
        print("Adquisición detenida")

    def serial_reader(self):
        t = 0
        while True:
            packet = self.ser.read(13)
            if len(packet) == 13 and packet[-1] == 0xFF and self.running:
                try:
                    values = struct.unpack('<hhhhhh', packet[:-1])
                    with self.lock:
                        for i in range(NUM_CHANNELS):
                            self.buffers[i].append(values[i])
                        self.time_buffer.append(t)
                    t += SAMPLE_INTERVAL_MS
                except Exception as e:
                    print("Error:", e)

    def update_plot(self):
        if not self.running:
            return
        with self.lock:
            t = list(self.time_buffer)
            for i in range(3):
                self.lines1[i].set_data(t, list(self.buffers[i]))
            for i in range(3, 6):
                self.lines2[i - 3].set_data(t, list(self.buffers[i]))
            self.ax1.set_xlim(t[0], t[-1])
            self.ax2.set_xlim(t[0], t[-1])
        self.canvas.draw()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SerialPlotter()
    window.show()
    sys.exit(app.exec_())
