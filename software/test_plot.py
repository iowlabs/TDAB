import csv
import matplotlib.pyplot as plt

# Nombre del archivo CSV
csv_file = "datos.csv"

# Listas para almacenar los datos
timestamps = []
channels = [[] for _ in range(6)]  # 6 canales

# Leer el archivo CSV
with open(csv_file, "r") as file:
    reader = csv.reader(file)
    next(reader)  # Saltar la cabecera

    for row in reader:
        timestamps.append(float(row[0]))  # Columna de tiempo
        for i in range(6):
            channels[i].append(int(row[i+1]))  # Canales de datos

# Graficar los datos
plt.figure(figsize=(10, 5))

for i in range(6):
    plt.plot(timestamps, channels[i], label=f"Canal {i+1}")

plt.xlabel("Tiempo (s)")
plt.ylabel("Valor")
plt.title("Datos cargados desde CSV")
plt.legend()
plt.grid()
plt.show()
