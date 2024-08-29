# preproccess.py
# Abre el archivo de entrada en modo lectura

#file_list = ["lpf_e1"]
file_list = ["lpf_e2_x10","lpf_e2_x1k","lpf_e2_x200k"]

for fn in file_list:
	with open(fn+'.csv', 'w') as f_output:
		f_output.write('f,a,p\n')
		with open(fn+'.txt', 'r') as f_input:
			# Abre el archivo de salida en modo escritura
			# Itera sobre cada línea del archivo de entrada
			for linea in f_input:
				# Reemplaza los caracteres '(' y ')' por ','
				linea_modificada = linea.replace('(', ',').replace(')', ' ').replace('dB',' ').replace('�', ' ')
				# Escribe la línea modificada en el archivo de salida
				f_output.write(linea_modificada)
	print(f"Proceso completado. Revisa '{fn}.csv'")
