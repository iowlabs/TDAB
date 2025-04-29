import sys
import serial
import csv
import time
import numpy as np
import pandas as pd
import collections
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QFileDialog, QVBoxLayout, QWidget
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
import pyqtgraph as pg


max_buff = 1000


class SerialReader(QThread):
	data_received = pyqtSignal(list)  # Señal para enviar datos a la GUI
	finished = pyqtSignal()

	def __init__(self, port, baudrate=500000,sampling_rate = 1000):
		super().__init__()
		self.port = port
		self.baudrate = baudrate
		self.sampling_rate = sampling_rate #datos por segundo
		self.running = True  # Para detener el hilo correctamente

	def run(self):
		try:
			with serial.Serial(self.port, self.baudrate, timeout=0) as ser, open("datos.csv", "w", newline="") as file:
				writer = csv.writer(file)
				writer.writerow(["T", "Ch1", "Ch2", "Ch3", "Ch4", "Ch5", "Ch6"])  # Encabezados del CSV

				#start_time = time.time()  # Marca de tiempo inicial
				sample_counter = 0
				start_time = time.perf_counter()  # Marca de tiempo inicial

				while self.running:
					line = ser.readline().decode('utf-8').strip()
					if line:
						try:
							data = list(map(int, line.split(",")))  # Convertir datos a enteros
							#timestamp = round(time.time() - start_time, 3)  # Tiempo relativo
							#timestamp = round(sample_counter / self.sampling_rate,3)  # Tiempo relativo
							timestamp = sample_counter  # Tiempo relativo
							sample_counter +=1

							data.insert(0, timestamp)  # Agregar el tiempo al inicio
							writer.writerow(data)  # Guardar en CSV
							self.data_received.emit(data)  # Enviar a la GUI
						except ValueError:
							print(f"Error al parsear: {line}")  # En caso de datos corruptos

		except serial.SerialException as e:
			print(f"Error con el puerto serial: {e}")

		self.finished.emit()

	def stop(self):
		self.running = False
		self.quit()
		self.wait()

class GraphWindow(QMainWindow):
	def __init__(self, port="/dev/ttyUSB0"):  # Cambia por tu puerto COM
		super().__init__()

		self.setWindowTitle("Visualizador de Datos en Tiempo Real")
		self.setGeometry(100, 100, 900, 600)

		# Layout principal
		layout = QVBoxLayout()
		self.main_widget = QWidget()
		self.setCentralWidget(self.main_widget)
		self.main_widget.setLayout(layout)

		# Crear el gráfico con pyqtgraph
		self.plot_widget = pg.PlotWidget()
		layout.addWidget(self.plot_widget)
		self.plot_widget.setLabel("left", "Valor")
		self.plot_widget.setLabel("bottom", "Tiempo (s)")
		self.plot_widget.addLegend()
		self.plot_widget.setDownsampling(mode='peak')

 		# Activar interactividad (zoom y pan)
		self.plot_widget.setMouseEnabled(x=True, y=True)  # Permitir zoom con la rueda del mouse
		self.plot_widget.getViewBox().setMouseMode(pg.ViewBox.RectMode)  # Habilitar modo de zoom rectangular


		# Configuración de curvas (6 canales)
		self.curves = []
		#self.data_buffer = {i: np.zeros(10000) for i in range(6)}  # Buffer de 10s
		self.time_buffer = collections.deque([0],max_buff)  # Buffer de tiempo

		#data to plots
		self.ch1_buff = collections.deque([0],max_buff)
		self.ch2_buff = collections.deque([0],max_buff)
		self.ch3_buff = collections.deque([0],max_buff)
		self.ch4_buff = collections.deque([0],max_buff)
		self.ch5_buff = collections.deque([0],max_buff)
		self.ch6_buff = collections.deque([0],max_buff)

		self.data_buffer = [self.ch1_buff,self.ch2_buff,self.ch3_buff,self.ch4_buff,self.ch5_buff,self.ch6_buff]

		colors = ['r', 'g', 'b', 'y', 'm', 'c']
		for i in range(6):
			curve = self.plot_widget.plot(pen=pg.mkPen(colors[i], width=2), name=f"Ch{i+1}")
			self.curves.append(curve)


		# Botón para detener la adquisición
		self.stop_button = QPushButton("Detener Adquisición", self)
		layout.addWidget(self.stop_button)
		self.stop_button.clicked.connect(self.stop_acquisition)

		# Botón para cargar el CSV y graficar
		self.load_button = QPushButton("Cargar CSV", self)
		layout.addWidget(self.load_button)
		self.load_button.clicked.connect(self.load_csv)

		# Botón para restablecer la vista
		self.reset_view_button = QPushButton("Restablecer Vista", self)
		layout.addWidget(self.reset_view_button)
		self.reset_view_button.clicked.connect(self.reset_view)


		# Inicializar el hilo de lectura
		self.serial_thread = SerialReader(port)
		self.serial_thread.data_received.connect(self.update_data)
		self.serial_thread.finished.connect(self.on_acquisition_stopped)
		self.serial_thread.start()

		#Actualizamos los graficos
		self.update_timer = QTimer()
		self.update_timer.timeout.connect(self.update_plot)
		self.update_timer.start(100)



	def update_data(self,data):
		""" Actualiza los gráficos con nuevos datos en tiempo real. """
		timestamp = data[0]  # Primer valor es el tiempo
		values = data[1:]  # Resto son valores de los canales

		# Desplazamiento de buffers
		self.time_buffer.append(timestamp)

		for i in range(6):
			self.data_buffer[i].append(values[i])


	def update_plot(self):
		""" Actualiza los gráficos con nuevos datos en tiempo real. """
		for i in range(6):
			self.curves[i].setData(self.time_buffer, self.data_buffer[i])  # Actualizar la curva

	def stop_acquisition(self):
		""" Detiene la adquisición de datos """
		if self.serial_thread.isRunning():
			self.serial_thread.stop()
			self.stop_button.setEnabled(False)  # Deshabilitar el botón

	def on_acquisition_stopped(self):
		""" Acción después de detener la adquisición """
		print("Adquisición detenida.")
		self.stop_button.setText("Adquisición Finalizada")

	def open_csv(self):
		""" Abre el CSV con un explorador de archivos. """
		file_name, _ = QFileDialog.getOpenFileName(self, "Abrir CSV", "", "Archivos CSV (*.csv)")
		if file_name:
			print(f"Abriendo {file_name}")

	def load_csv(self):
		""" Carga y grafica los datos del archivo CSV """
		file_name, _ = QFileDialog.getOpenFileName(self, "Abrir CSV", "", "Archivos CSV (*.csv)")
		if not file_name:
			return

		try:
			df = pd.read_csv(file_name)
			self.plot_widget.clear()  # Limpiar la gráfica antes de cargar los datos

			colors = ['r', 'g', 'b', 'y', 'm', 'c']
			for i in range(1, 7):  # Las columnas Ch1 a Ch6
				self.plot_widget.plot(df["T"], df[f"Ch{i}"], pen=pg.mkPen(colors[i-1], width=2), name=f"Ch{i}")

			print(f"CSV cargado correctamente: {file_name}")

		except Exception as e:
			print(f"Error al cargar el CSV: {e}")

	def reset_view(self):
		""" Restablece la vista de la gráfica """
		self.plot_widget.getViewBox().autoRange()  # Ajusta el zoom automáticamente


	def closeEvent(self, event):
		""" Asegura que el hilo se cierre correctamente al cerrar la ventana. """
		self.serial_thread.stop()
		event.accept()

if __name__ == "__main__":
	app = QApplication(sys.argv)
	window = GraphWindow(port="/dev/ttyACM0")  # Cambia por el puerto correcto en tu sistema
	window.show()
	sys.exit(app.exec_())
