# -*- coding: utf-8 -*-
import time
import serial
import json
import threading
import sys, getopt
import re
import numpy as np
import matplotlib.pyplot as plt
import collections
import csv
import datetime

v1 = np.zeros(1000)
v2 = np.zeros(1000)
v3 = np.zeros(1000)
v4 = np.zeros(1000)
v5 = np.zeros(1000)
v6 = np.zeros(1000)




class tdab:
	def __init__(self,id,com):
		self.id  =  id
		self.debug 			= False
		self.port_name 		= com
		self.baud_rate 		= 500000
		self.arduino_com  	= None    #serial com
		self.arduino_thread = None
		self.connected    	= False  #false = not connected,  true = connected
		self.incomming_msg  = ""
		self.data_ready = False
		self.counter = 0
		self.read_flag = False
		self.v1 = 0 # np.zeros(1000)
		self.v2 = 0 # np.zeros(1000)
		self.v3 = 0 # np.zeros(1000)
		self.v4 = 0 # np.zeros(1000)
		self.v5 = 0 # np.zeros(1000)
		self.v6 = 0 # np.zeros(1000)
		self.time_v	= collections.deque([0.0],1000)
		self.ch1_v  = collections.deque([0.0],1000)
		self.ch2_v  = collections.deque([0.0],1000)
		self.ch3_v 	= collections.deque([0.0],1000)
		self.ch4_v 	= collections.deque([0.0],1000)
		self.ch5_v  = collections.deque([0.0],1000)
		self.ch6_v  = collections.deque([0.0],1000)
		self.save = False
		self.file_name = "test"+".csv"
		self.data_file = None
		self.data_writer = None

	def connectSerialPort(self):
		try:
			self.arduino_com = serial.Serial(self.port_name,self.baud_rate,timeout = 0.1)
			self.connected = True
			self.arduino_thread = threading.Thread(target = self.arduinoRCV,)
			self.arduino_thread.deamon = True
			self.arduino_thread.start()
			self.arduino_thread.join(0.1)
			print(f"tdab {self.id} connected to port {self.port_name}")
		except Exception as e:
			self.connected = False
			print(f"failed to connect {self.id} to port {self.port_name}")
			print(e)

	def disconnectSerialPort(self):
		try:
			self.arduino_com.close()
			self.connected = False
		except Exception as e:
			print("Not COM available")

	def sendMsg(self, cmd, arg):
		msg = json.dumps({"cmd":cmd,"arg":arg})
		print(f'tdab enviando mensaje:{msg}')
		if self.arduino_com.isOpen():
			self.arduino_com.write(msg.encode('ascii'))
			#self.arduino_com.flush()

	def arduinoRCV(self):
		temp = ""
		while self.connected:
			try:
				if self.arduino_com.isOpen():
					if self.read_flag:
						self.incomming_msg += self.arduino_com.readline().decode("utf-8")
						if self.incomming_msg != "":
							temp = self.incomming_msg.strip().split(',')
							self.incomming_msg = ""
							if len(temp) == 6:
								self.v1 = int(temp[0])
								self.v2 = int(temp[1])
								self.v3 = int(temp[2])
								self.v4 = int(temp[3])
								self.v5 = int(temp[4])
								self.v6 = int(temp[5])
								self.ch1_v.append(self.v1)
								self.ch2_v.append(self.v2)
								self.ch3_v.append(self.v3)
								self.ch4_v.append(self.v4)
								self.ch5_v.append(self.v5)
								self.ch6_v.append(self.v6)
								if self.save :
									self.data_writer.writerow([self.v1,self.v2,self.v3,self.v4,self.v5,self.v6])
								self.counter += 1
								self.data_ready = True
								#print(self.counter)


					#    data = re.findall(r"[-+]?\d*\.\d+|\d+",self.incomming_msg)
					#    self.actual_value = float(data[0])
					#    if self.actual_value == "":
					#        self.actual_value = -127;
					#    #data =  json.loads(self.incomming_msg)
					#    #print(f"{self.id} valor actual : {float(self.actual_value[0])}")
					#    self.incomming_msg =""
				else:
					pass
			except  Exception as e:
				pass
				#print (e)
	"""
	def plotData(self):
		print("making plots")
		x = np.linspace(0, 1000, 1000, endpoint = False)
		plt.figure()

		plt.plot(x.v1, label='Canal 1', color='b')
		plt.plot(x,v2, label='Canal 2', color='g')
		plt.plot(x,v3, label='Canal 3', color='r')
		plt.plot(x,v4, label='Canal 4', color='c')
		plt.plot(x,v5, label='Canal 5', color='m')
		plt.plot(x,v6, label='Canal 6', color='y')

		# Añadir la leyenda
		plt.legend()

		# Añadir título y etiquetas de los ejes
		plt.title('Channel test')
		plt.xlabel('Samples')
		plt.ylabel('Value')
		plt.grid()

		# Mostrar el gráfico
		plt.show()
	"""
	def startSave(self,_path):
		time_now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
		self.file_name = _path+"test_"+time_now+".csv"
		self.data_file = open(self.file_name,"w",newline = '')
		self.data_writer = csv.writer(self.data_file)
		self.save = True

	def stopSave(self):
		self.save = False
		self.data_file.close()

	def stopRcvr(self):
		print("Closing")
		self.connected = False
		self.arduino_com.close()

if __name__ == "__main__":
	COM = "/dev/ttyUSB0"

	try:
		opts,args = getopt.getopt(sys.argv[1:],"hp:i:")
	except:
		print("Comando no valido pruebe -h por ayuda")
		sys.exit(2)

	for opt ,arg in opts:
		if opt == '-h':
			print("main.py -h for help -p <com> for port to connect")
			sys.exit()
		elif opt =='-p':
			COM = arg
			print(f"trying to connect to port {COM}")
		elif opt == '-i':
			print("option i")


	nodo = tdab("b1",COM)
	nodo.connectSerialPort()
	time.sleep(1)
	nodo.counter = 0
	nodo.ready_flag = False
	nodo.startSave("data/")
	nodo.sendMsg("start",{})
	nodo.read_flag  = True
	start_time = time.time()
	time.sleep(5)
	nodo.stopSave()
	nodo.sendMsg("stop",{})
	print("datos transferidos {}".format(nodo.counter))
	stop_time = time.time()
	print("tiempo total transcurrido {} ".format(stop_time - start_time))
	nodo.stopRcvr()
	print("making plots")
	x = np.linspace(0, 1000, 1000, endpoint = False)
	plt.figure()

	plt.plot(x,nodo.ch1_v, label='Canal 1', color='b')
	plt.plot(x,nodo.ch2_v, label='Canal 2', color='g')
	plt.plot(x,nodo.ch3_v, label='Canal 3', color='r')
	plt.plot(x,nodo.ch4_v, label='Canal 4', color='c')
	plt.plot(x,nodo.ch5_v, label='Canal 5', color='m')
	plt.plot(x,nodo.ch6_v, label='Canal 6', color='y')

	# Añadir la leyenda
	plt.legend()

	# Añadir título y etiquetas de los ejes
	plt.title('Channel test')
	plt.xlabel('Samples')
	plt.ylabel('Value')
	plt.grid()

	# Mostrar el gráfico
	plt.show()
