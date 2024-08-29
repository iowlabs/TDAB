#test plot.py
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

#file_list = ["lpf_e1"]
file_list = ["lpf_e2_x10","lpf_e2_x1k","lpf_e2_x200k"]


for fn in file_list:
	# Lee el archivo CSV
	df = pd.read_csv(fn+'.csv')

	# Extrae los datos de frecuencia, amplitud y fase
	frecuencia = df['f']
	amplitud = df['a']
	fase = df['p']

	# Grafica el diagrama de Bode
	fig, axs = plt.subplots(2, 1, figsize=(10, 8))
	axs[0].semilogx(frecuencia,amplitud)
	axs[0].set_ylabel('Amplitud (dB)')
	axs[0].grid(True)
	axs[1].semilogx(frecuencia, fase)
	axs[1].set_xlabel('Frecuencia (Hz)')
	axs[1].set_ylabel('Fase (grados)')
	axs[1].grid(True)
	#fig.suptitle("LPF Etapa 1")
	fig.suptitle("LPF Etapa 2, R = "+fn.replace("lpf_e2_x",""))
	fig.savefig('img/'+fn+'.png')
	plt.close()
