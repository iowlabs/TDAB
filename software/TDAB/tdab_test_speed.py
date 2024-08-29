# -*- coding: utf-8 -*-
import time
import serial
import json
import threading
import sys, getopt
import re
import numpy as np
import matplotlib.pyplot as plt


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
		self.counter = 0
		self.read_flag = False
		self.v1 = np.zeros(1000)
		self.v2 = np.zeros(1000)
		self.v3 = np.zeros(1000)
		self.v4 = np.zeros(1000)
		self.v5 = np.zeros(1000)
		self.v6 = np.zeros(1000)


	def connectSerialPort(self):
		try:
			self.arduino_com = serial.Serial(self.port_name, self.baud_rate, timeout = 0.1)
			self.connected = True
			self.arduino_thread = threading.Thread(target = self.arduinoRCV,)
			self.arduino_thread.deamon = True
			self.arduino_thread.start()
			self.arduino_thread.join(0.1)
			print(f"licometro {self.id} connected to port {self.port_name}")
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

		if self.arduino_com.isOpen():
			print(f'licometro enviando mensaje:{msg}')
			self.arduino_com.write(msg.encode('ascii'))
			self.arduino_com.flush()

	def arduinoRCV(self):
		temp = ""
		while self.connected:
			try:
				if self.arduino_com.isOpen():

					self.incomming_msg += self.arduino_com.readline().decode("utf-8")
					if self.incomming_msg != "":
						temp = self.incomming_msg.strip().split(',')
						self.incomming_msg = ""
						self.v1[self.counter] = int(temp[0])
						self.v2[self.counter] = int(temp[1])
						self.v3[self.counter] = int(temp[2])
						self.v4[self.counter] = int(temp[3])
						self.v5[self.counter] = int(temp[4])
						self.v6[self.counter] = int(temp[5])
						self.counter += 1
						if self.counter>=1000:
							self.counter = 0;
				else:
					pass
			except  Exception as e:
				pass
				#print (e)
	def plotData(self):
		print("making plots")
		x = np.linspace(0, 1000, 1000, endpoint = False)
		plt.figure()

		plt.plot(x,self.v1, label='Canal 1', color='b')
		plt.plot(x,self.v2, label='Canal 2', color='g')
		plt.plot(x,self.v3, label='Canal 3', color='r')
		plt.plot(x,self.v4, label='Canal 4', color='c')
		plt.plot(x,self.v5, label='Canal 5', color='m')
		plt.plot(x,self.v6, label='Canal 6', color='y')

		# Añadir la leyenda
		plt.legend()

		# Añadir título y etiquetas de los ejes
		plt.title('Channel test')
		plt.xlabel('Samples')
		plt.ylabel('Value')
		plt.grid()

		# Mostrar el gráfico
		plt.show()

	def stopRcvr(self):
		print("Closing")
		self.connected = False
		self.arduino_com.close()

if __name__ == "__main__":
	COM = "/dev/ttyUSB0"
	#COM ="/dev/ttyACM0"

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

	time.sleep(1)
	nodo.counter = 0
	nodo.ready_flag = False
	nodo.read_flag  = True
	nodo.connectSerialPort()
	nodo.sendMsg("get",{})
	time.sleep(5)
	nodo.plotData()
	nodo.stopRcvr()
