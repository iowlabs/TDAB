# -*- coding: utf-8 -*-
from PyQt5 import QtCore,QtGui,QtWidgets
from PyQt5.QtWidgets import  QMainWindow, QApplication, QFileDialog

from TDAB.gui import Ui_MainWindow
from TDAB.tdab import tdab

from pyqtgraph import PlotWidget, plot
import pyqtgraph as pg
from time import sleep
from pandas import *
from simple_pid import PID
import numpy as np
import csv
import sys, getopt
import os
import time
from datetime import datetime,timedelta
import serial
import serial.tools.list_ports
import json
import threading
import collections



#COM_PORT    = '/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_756363131373511002C0-if00'
COM_PORT    = '/dev/ttyUSB0'
DATA_PATH   = "data/"

debug = True

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

RUNNING = 1
STOPPED = 0

class MainWindow(QtWidgets.QMainWindow):
	def __init__(self):
		super(MainWindow,self).__init__()
		self.ui = Ui_MainWindow()
		self.ui.setupUi(self)
		self.setWindowTitle("Electro Fisiología")

		self.com_port	= COM_PORT
		self.controller = tdab("b1",self.com_port)
		self.sample_time = 1
		self.time_v = np.linspace(0, 1000, 1000, endpoint = False)
		pen = pg.mkPen(color = (0, 0, 255),width = 2)
		self.collections 	= [	self.controller.ch1_v,
								self.controller.ch2_v,
								self.controller.ch3_v,
								self.controller.ch4_v,
								self.controller.ch5_v,
								self.controller.ch6_v]

		#self.collectionsAcc = [self.acc1_v,self.acc2_v]
		self.graphicsCh =  [self.ui.graphicsView_9]
		#self.graphicsAcc = [self.ui.graphicsView_13,self.ui.graphicsView_16]

		for i in range(1):
			self.graphicsCh[i].setBackground('w')
			#self.graphicsCh[i].setTitle(self.plot_titles[i],color = "b",size = "15pt")

			styles = {"color": "#f00", "font-size": "10px"}
			#self.graphicsCh[i].setLabel("left", self.plot_labels[i], **styles)
			#self.graphicsCh[i].setLabel("bottom", "tiempo (s)", **styles)
			self.graphicsCh[i].showGrid(x=True, y=True)

			#Set Range
			self.graphicsCh[i].setXRange(-0.05, 1.05, padding=0)
			self.graphicsCh[i].setYRange(-0.05, 1.05, padding=0)
			self.graphicsCh[i].plot([0], self.collections[i], pen=pen)

		#for i in range(2):
		#	self.graphicsAcc[i].setBackground('w')
		#	#self.graphicsCh[i].setTitle(self.plot_titles[i],color = "b",size = "15pt")
		#
		#	styles = {"color": "#f00", "font-size": "10px"}
		#	#self.graphicsCh[i].setLabel("left", self.plot_labels[i], **styles)
		#	self.graphicsAcc[i].setLabel("bottom", "tiempo (s)", **styles)
		#	self.graphicsAcc[i].showGrid(x=True, y=True)

		#	#Set Range
		#	self.graphicsAcc[i].setXRange(-0.05, 1.05, padding=0)
		#	self.graphicsAcc[i].setYRange(-0.05, 1.05, padding=0)
		#	self.graphicsAcc[i].plot(self.time_v, self.collectionsAcc[i], pen=pen)


		self.time_now   = ""
		self.elapsed_time = 0

		self.file_name      = ""
		self.path           = DATA_PATH
		self.data_path 		= "./data/"
		self.data_file      = None
		self.data_writer    = None
		self.label_time     = ""

		self.state = STOPPED

		self.enable_ch		= [ 0, 0, 0, 0, 0, 0, 0, 0]
		self.bfc 	= [ EEG_BFC, EEG_BFC, EEG_BFC, EEG_BFC, EEG_BFC, EEG_BFC ]
		self.tfc 	= [ EEG_TFC, EEG_TFC, EEG_TFC, EEG_TFC, EEG_TFC, EEG_TFC ]
		self.gain 	= [ EEG_GAIN, EEG_GAIN, EEG_GAIN, EEG_GAIN, EEG_GAIN, EEG_GAIN ]

		self.mode_ch = [ 0, 0, 0, 0, 0, 0] # 0 test; 1 impedance
		self.test_mode_ch = ['EEG','EEG','EEG','EEG','EEG','EEG']
		"""-----------------------
   			INITIAL DISABLED
		----------------------"""

		self.ui.pushButton_16.setDisabled(True)
		self.ui.pushButton_19.setDisabled(True)

		self.ui.pushButton_5.setDisabled(True)
		self.ui.pushButton_20.setDisabled(True)

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

		self.sound_btns = [	self.ui.pushButton_14,
							self.ui.pushButton_13,
							self.ui.pushButton_12,
							self.ui.pushButton_11,
							self.ui.pushButton_10,
							self.ui.pushButton_15]

		self.bfc_text = [	self.ui.label_36,
							self.ui.label_48,
							self.ui.label_45,
							self.ui.label_41,
							self.ui.label_32,
							self.ui.label_52]

		self.tfc_text = [	self.ui.label_35,
							self.ui.label_47,
							self.ui.label_44,
							self.ui.label_40,
							self.ui.label_31,
							self.ui.label_51]

		self.gain_text = [	self.ui.label_37,
							self.ui.label_49,
							self.ui.label_46,
							self.ui.label_42,
							self.ui.label_33,
							self.ui.label_53]

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
			self.sound_btns[i].setDisabled(True)
			self.impedancia_btn[i].setDisabled(True)
			self.test_btn[i].setDisabled(True)
			self.cb_test[i].setDisabled(True)
			self.set_btns[i].setDisabled(True)
			self.sound_btns[i].setDisabled(True)
			self.bfc_text[i].setDisabled(True)
			self.tfc_text[i].setDisabled(True)
			self.gain_text[i].setDisabled(True)
			self.bfc_lines[i].setDisabled(True)
			self.tfc_lines[i].setDisabled(True)
			self.gain_lines[i].setDisabled(True)

		self.ui.pushButton_8.setDisabled(False)
		self.ui.pushButton_9.setDisabled(True)


		"""--------------------------
    		Comportamiento General
		-----------------------------"""

		#ENABLES CHANNELS
		self.enchannels_checks[0].stateChanged.connect(lambda:self.enableChannel(0))
		self.enchannels_checks[1].stateChanged.connect(lambda:self.enableChannel(1))
		self.enchannels_checks[2].stateChanged.connect(lambda:self.enableChannel(2))
		self.enchannels_checks[3].stateChanged.connect(lambda:self.enableChannel(3))
		self.enchannels_checks[4].stateChanged.connect(lambda:self.enableChannel(4))
		self.enchannels_checks[5].stateChanged.connect(lambda:self.enableChannel(5))

		#SET IMPEDANCE MODE
		self.impedancia_btn[0].clicked.connect(lambda:self.impedanceMode(0))
		self.impedancia_btn[1].clicked.connect(lambda:self.impedanceMode(1))
		self.impedancia_btn[2].clicked.connect(lambda:self.impedanceMode(2))
		self.impedancia_btn[3].clicked.connect(lambda:self.impedanceMode(3))
		self.impedancia_btn[4].clicked.connect(lambda:self.impedanceMode(4))
		self.impedancia_btn[5].clicked.connect(lambda:self.impedanceMode(5))

		#SET TEST MODE
		self.test_btn[0].clicked.connect(lambda:self.testMode(0))
		self.test_btn[1].clicked.connect(lambda:self.testMode(1))
		self.test_btn[2].clicked.connect(lambda:self.testMode(2))
		self.test_btn[3].clicked.connect(lambda:self.testMode(3))
		self.test_btn[4].clicked.connect(lambda:self.testMode(4))
		self.test_btn[5].clicked.connect(lambda:self.testMode(5))

		#SELECT TEST TYPE
		self.cb_test[0].currentIndexChanged.connect(lambda:self.changeType(0))
		self.cb_test[1].currentIndexChanged.connect(lambda:self.changeType(1))
		self.cb_test[2].currentIndexChanged.connect(lambda:self.changeType(2))
		self.cb_test[3].currentIndexChanged.connect(lambda:self.changeType(3))
		self.cb_test[4].currentIndexChanged.connect(lambda:self.changeType(4))
		self.cb_test[5].currentIndexChanged.connect(lambda:self.changeType(5))

		#RUN TEST
		self.ui.pushButton_8.clicked.connect(self.startTest)
		self.ui.pushButton_9.clicked.connect(self.stopTest)

		#CHANGE DIRECTORY
		self.ui.pushButton_7.clicked.connect(self.changeDir)

		#PLAY SOUND
		self.sound_btns[0].clicked.connect(lambda:self.playChannel(0))
		self.sound_btns[1].clicked.connect(lambda:self.playChannel(1))
		self.sound_btns[2].clicked.connect(lambda:self.playChannel(2))
		self.sound_btns[3].clicked.connect(lambda:self.playChannel(3))
		self.sound_btns[4].clicked.connect(lambda:self.playChannel(4))
		self.sound_btns[5].clicked.connect(lambda:self.playChannel(5))

		#SET PARAMETERS
		self.set_btns[0].clicked.connect(lambda:self.setParameters(0))
		self.set_btns[1].clicked.connect(lambda:self.setParameters(1))
		self.set_btns[2].clicked.connect(lambda:self.setParameters(2))
		self.set_btns[3].clicked.connect(lambda:self.setParameters(3))
		self.set_btns[4].clicked.connect(lambda:self.setParameters(4))
		self.set_btns[5].clicked.connect(lambda:self.setParameters(5))

		#INITIAL VALUES
		for i in range(6):
			self.bfc_lines[i].setText(str(self.bfc[i]))
			self.tfc_lines[i].setText(str(self.tfc[i]))
			self.gain_lines[i].setText(str(self.gain[i]))


		#TIME
		self.date_now = QtCore.QDate.currentDate()
		#MGMT OF TIME
		self.clock_timer = QtCore.QTimer()
		self.clock_timer.setInterval(1000)
		self.clock_timer.timeout.connect(self.updateTime)
		self.clock_timer.start()

		#MGMT NEW DATA
		self.run_timer = QtCore.QTimer()
		self.run_timer.setInterval(1000*self.sample_time)
		self.run_timer.timeout.connect(self.updateData)


	def enableChannel(self, _ch):
		if self.enchannels_checks[_ch].isChecked():
			print("canal {} habilitado".format(_ch+1))
			self.enable_ch[_ch] = 1
			self.sound_btns[_ch].setDisabled(False)
			if self.mode_ch[_ch]:
				self.impedancia_btn[_ch].setDisabled(True)
				self.test_btn[_ch].setDisabled(False)
			else:
				self.impedancia_btn[_ch].setDisabled(False)
				self.test_btn[_ch].setDisabled(True)
			self.cb_test[_ch].setDisabled(False)
			self.set_btns[_ch].setDisabled(False)
			self.sound_btns[_ch].setDisabled(False)
			self.bfc_text[_ch].setDisabled(False)
			self.tfc_text[_ch].setDisabled(False)
			self.gain_text[_ch].setDisabled(False)
			self.bfc_lines[_ch].setDisabled(False)
			self.tfc_lines[_ch].setDisabled(False)
			self.gain_lines[_ch].setDisabled(False)
		else:
			print("canal {} deshabilitado".format(_ch))
			self.enable_ch[_ch] = 0
			self.sound_btns[_ch].setDisabled(True)
			self.impedancia_btn[_ch].setDisabled(True)
			self.test_btn[_ch].setDisabled(True)
			self.cb_test[_ch].setDisabled(True)
			self.set_btns[_ch].setDisabled(True)
			self.sound_btns[_ch].setDisabled(True)
			self.bfc_text[_ch].setDisabled(True)
			self.tfc_text[_ch].setDisabled(True)
			self.gain_text[_ch].setDisabled(True)
			self.bfc_lines[_ch].setDisabled(True)
			self.tfc_lines[_ch].setDisabled(True)
			self.gain_lines[_ch].setDisabled(True)

	def impedanceMode(self,_ch ):
		self.mode_ch[_ch] = 1
		self.impedancia_btn[_ch].setDisabled(True)
		self.test_btn[_ch].setDisabled(False)

	def testMode(self,_ch ):
		self.mode_ch[_ch] = 0
		self.impedancia_btn[_ch].setDisabled(False)
		self.test_btn[_ch].setDisabled(True)

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

	def updateTime(self):
		if self.state == RUNNING:
			self.elapsed_time += 1
			self.ui.lineEdit_3.setText(str(timedelta(seconds = self.elapsed_time)))
		now = datetime.now()
		current_time = now.strftime("%H:%M:%S")
		self.ui.lineEdit_2.setText(current_time)

	def updateData(self):
		self.graphicsCh[0].clear()
		x = np.linspace(0, 1000, 1000, endpoint = False)
		#pen = pg.mkPen(color = (0, 0, 255),width = 2)
		self.graphicsCh[0].plot(x, self.collections[0], pen = pg.mkPen(color = (0, 0, 255),width = 2))
		self.graphicsCh[0].plot(x, self.collections[1], pen = pg.mkPen(color = (255, 0, 0),width = 2))
		self.graphicsCh[0].plot(x, self.collections[2], pen = pg.mkPen(color = (0, 255, 0),width = 2))
		self.graphicsCh[0].plot(x, self.collections[3], pen = pg.mkPen(color = (0, 255, 255),width = 2))
		self.graphicsCh[0].plot(x, self.collections[4], pen = pg.mkPen(color = (255, 0, 255),width = 2))
		self.graphicsCh[0].plot(x, self.collections[5], pen = pg.mkPen(color = (255, 255, 0),width = 2))


	def setParameters(self , _ch):
		if self.enable_ch[_ch]:
			print("sending parameters for channels {}".format(_ch))
			if self.mode_ch[_ch]:
				try:
					#ENABLE CHANNEL
					arg = {"ch":_ch,"state":1}
					self.controller.sendMsg("ench",arg)
					#SET BFC
					arg = {"ch":_ch,"bfc":self.bfc[_ch]}
					self.controller.sendMsg("set_bfc",arg)
					#SET TFC
					arg = {"ch":_ch,"tfc":self.tfc[_ch]}
					self.controller.sendMsg("set_tfc",arg)
					#SET GAIN
					arg = {"ch":_ch,"gain":self.gain[_ch]}
					self.controller.sendMsg("set_gain",arg)
				except Exception as e:
					print(e)
		else:
			print("channel not enabled")


	def playChannel(self, _ch):
		print("playng sound on channel {}".format(_ch))

	def startTest(self):
		self.state = RUNNING
		self.elapsed_time = 0
		self.ui.pushButton_8.setDisabled(True)
		self.ui.pushButton_9.setDisabled(False)
		self.controller.connectSerialPort()
		time.sleep(1)
		self.controller.counter = 0
		self.controller.ready_flag = False
		self.controller.startSave(self.data_path)
		self.controller.sendMsg("start",{})
		self.controller.read_flag  = True


	def stopTest(self):
		self.state = STOPPED
		self.elapsed_time = 0
		self.ui.pushButton_8.setDisabled(False)
		self.ui.pushButton_9.setDisabled(True)
		self.controller.stopSave()
		self.controller.sendMsg("stop",{})
		self.updateData()

	def changeDir(self):
		self.data_path = QFileDialog.getExistingDirectory(self, caption = 'Seleccione nuevo directorio',directory = DATA_PATH)+"/"
		self.ui.lineEdit.setText(self.data_path)

	def Close(self):
		try:
			self.run_timer.stop()
			self.controller.stopRcvr()
		except Exception as e:
			print("Controller not connected. Closing")


if __name__ == "__main__":
	app = QtWidgets.QApplication([])
	main = MainWindow()
	main.show()
	#main.showFullScreen()

	ret = app.exec_()
	main.Close()
	print("stoped")
	sys.exit(ret)
