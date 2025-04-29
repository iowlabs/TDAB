import serial
import json
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque
import threading
import time
import datetime
import csv

# Configuración del puerto serial
SERIAL_PORT = '/dev/ttyUSB0'  # Cambia esto al puerto adecuado (e.g., '/dev/ttyUSB0' en Linux)
BAUD_RATE = 115200
TIMEOUT = 1
PATH 	= '/data/'


# Tamaño máximo de los buffers
MAX_LEN = 1000  # Ajusta según tus necesidades

# Buffers circulares para almacenar los datos
tiempo_buffer = deque(maxlen=MAX_LEN)
temp_buffer = deque(maxlen=MAX_LEN)
pwm_buffer = deque(maxlen=MAX_LEN)
sp_buffer =  deque(maxlen=MAX_LEN)

# Variable para controlar el hilo de lectura
running = True
file_name = ""


def saveData(_d1,_d2,_d3,_d4,_d5):
	with open(file_name, mode = 'a', newline='') as csv_file:
		writer_csv = csv.writer(csv_file)
		writer_csv.writerow([_d1,_d2,_d3,_d4,_d5])

def serial_reader():
	global running
	try:
		ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=TIMEOUT)
		print(f"Conectado al puerto serial: {SERIAL_PORT}")
	except serial.SerialException as e:
		print(f"Error al abrir el puerto serial: {e}")
		return

	while running:
		try:
			if ser.in_waiting > 0:
				line = ser.readline().decode('utf-8').strip()
				if line:
					try:
						data = json.loads(line)
						print(data)
						t = data['time']
						x = data['x']
						y = data['y']
						z = data['z']

						tiempo_buffer.append(t)
						x_buffer.append(x)
						y_buffer.append(y)
						z_buffer.append(z)
						#saveData(t,temp,temp_sp,pwm,rpm)
					except (json.JSONDecodeError, KeyError) as e:
						print(f"Error al procesar la línea: {line} | Error: {e}")
		except serial.SerialException as e:
			print(f"Error en la comunicación serial: {e}")
			break
		except UnicodeDecodeError as e:
			print(f"Error de decodificación: {e}")
		time.sleep(0.01)  # Pequeña pausa para evitar uso excesivo de CPU

	ser.close()
	print("Hilo de lectura serial terminado.")

# Iniciar el hilo de lectura serial
file_name = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")+".csv"
thread = threading.Thread(target=serial_reader, daemon=True)
thread.start()

# Configuración de la gráfica
fig, ax = plt.subplots()
line1, = ax.plot([], [], label="ax", color='tab:blue')
line2, = ax.plot([], [], label="ay", color='tab:green')
line3, = ax.plot([], [], label="az", color='tab:red')

ax.set_xlabel('Tiempo')
ax.set_ylabel('Accel')
ax.legend()
ax.grid(True)

# Inicialización de la gráfica
def init():
	ax.set_xlim(0, 10)  # Ventana inicial de tiempo
	ax.set_ylim(0, 10)  # Ajusta según tus datos
	line1.set_data([], [])
	line2.set_data([], [])
	line3.set_data([], [])

	return line1, line2, line3

# Actualización de la gráfica
def update(frame):
	if tiempo_buffer:
		# Obtener los datos actuales
		tiempos = list(tiempo_buffer)
		ax_list = list(x_buffer)
		ay_list = list(y_buffer)
		az_list = list(z_buffer)
		#print(len(voltajes))

		# Actualizar las líneas de la gráfica
		line1.set_data(tiempos, ax_list)
		line2.set_data(tiempos, ay_list)
		line3.set_data(tiempos, az_list)
		# Ajustar los límites de la gráfica
		ax.set_xlim(tiempos[0], tiempos[-1] + 1)
		y_min = min(min(ax_list, default=0), min(ay_list, default=0), min(az_list,default = 0)) - 1
		y_max = max(max(ax_list, default=10), max(ay_list, default=10),max(az_list, default=10) ) + 1
		#y_max = max(temperaturas, default=10) + 1
		ax.set_ylim(y_min, y_max)
		ax.set_title("Temp ctrol incubadora")


	return line1, line2

# Configuración de la animación
ani = animation.FuncAnimation(fig, update, init_func=init, blit=False, interval=100)

# Función para cerrar el programa limpiamente
def on_close(event):
    global running
    print("Cerrando la aplicación...")
    running = False
    thread.join()

# Conectar el evento de cierre de la figura
fig.canvas.mpl_connect('close_event', on_close)

# Mostrar la gráfica
plt.show()
