import sys
import json
import serial
import collections
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import QTimer
import pyqtgraph as pg

PORT = '/dev/ttyACM0'  # Ajusta esto a tu puerto en Linux o COMx en Windows
BAUD = 115200
BUFFER_SIZE = 1000  # 1 segundo de datos a 1kHz

class RealTimePlot(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Acelerómetro MPU9250")

        self.plot = pg.PlotWidget()
        self.setCentralWidget(self.plot)

        self.plot.addLegend()
        self.plot.setLabel('left', 'Aceleración (g)')
        self.plot.setLabel('bottom', 'Tiempo (s)')

        self.curves = {
            'x': self.plot.plot(pen='r', name='Acc X'),
            'y': self.plot.plot(pen='g', name='Acc Y'),
            'z': self.plot.plot(pen='b', name='Acc Z')
        }

        self.data = {
            'time': collections.deque(maxlen=BUFFER_SIZE),
            'x': collections.deque(maxlen=BUFFER_SIZE),
            'y': collections.deque(maxlen=BUFFER_SIZE),
            'z': collections.deque(maxlen=BUFFER_SIZE),
        }

        self.serial = serial.Serial(PORT, BAUD, timeout=0.1)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(10)  # Actualiza el gráfico cada 10 ms (~100 FPS)

    def update_plot(self):
        while self.serial.in_waiting:
            line = self.serial.readline().decode('utf-8').strip()
            try:
                #packet = json.loads(line)
                #t_ms = packet['time']
                #t_sec = (t_ms - self.data['time'][0]) / 1000 if self.data['time'] else 0
				if not hasattr(self, 'sample_counter'):
					self.sample_counter = 0
				t_sec = self.sample_counter / 1000.0  # a 1 kHz
				self.sample_counter += 1
				self.data['time'].append(t_sec)
				acc = packet['acc']
                #self.data['time'].append(t_sec)
                self.data['x'].append(acc['x'])
                self.data['y'].append(acc['y'])
                self.data['z'].append(acc['z'])
            except Exception as e:
                print(f"Error: {e} | Línea: {line}")

        for axis in ['x', 'y', 'z']:
            self.curves[axis].setData(self.data['time'], self.data[axis])

    def closeEvent(self, event):
        self.serial.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = RealTimePlot()
    win.show()
    sys.exit(app.exec_())
