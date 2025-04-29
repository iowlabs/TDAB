# Tremor Detection Adquisition Board

This device developed is an acquisition board for reading biometric signals from the human body, such as an EEG or EMG.

The board is based on the ADS1299, a 24-bit low-noise analog-to-digital converter developed for applications working with biopotential signals. The board uses a Teensy 4.1 as a DSP microcontroller to perform the tasks of synchronization, parameter configuration, ADC reading, and communication with the host.

The main feature of this equipment is that it has 6 analog signal conditioning channels that are fully configurable by software.

Each channel implements a band-pass filter whose gain and cut-off frequencies can be configured. The band-pass filter is implemented by two independent filters in cascade, one high-pass and one low-pass.

![pcb of TDAB ](https://github.com/iowlabs/TDAB/blob/main/electronics/EEG_board/EEG_board/output_files/tdab.png)


## Features
- 1ksps sampling rate
- 6 independent operating channels
- Bandpass configurable filter
	- Configurable lower cutoff frequency between 0.5Hz and 50Hz.
	- Gonfigurable upper cutoff frequency between 100Hz and 10kHz.
	- Configurable channel gain.
- Software-configurable channels
- 24-bit ADC and sampling rate up to 16kHz
- 16-bit accelerometer reading and up to 200g 9DoF
- Real-time reading and data display interface.




## LICENSES


| Item     | License 	|
|----------|------------|
| Hardware | CERN-OHL-S-2.0 |
| Software | GPL-3.0-or-later|
| Firmware | GPL-3.0-or-later|
| Documentation | CC-BY-SA-4.0|




## Hardware description


## Electrónics



### Schematics

### Layout

### BOM

## 3D Model

## Firmware

## Software
