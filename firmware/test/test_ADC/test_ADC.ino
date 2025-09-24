#include <SPI.h>

#define ADS_CS     10
#define ADS_DRDY    9
#define ADS_RESET   29
#define ADS_START   8

const int NUM_CHANNELS = 6; // canales que vamos a leer
volatile bool dataReady = false;

void drdyISR() {
  dataReady = true;
}

void setup() {
  Serial.begin(115200); // Puedes subir esto hasta 1 Mbps si lo necesitas

  pinMode(ADS_CS, OUTPUT);
  pinMode(ADS_RESET, OUTPUT);
  pinMode(ADS_START, OUTPUT);
  pinMode(ADS_DRDY, INPUT);

  digitalWrite(ADS_CS, HIGH);
  digitalWrite(ADS_RESET, HIGH);
  digitalWrite(ADS_START, LOW);

  SPI.begin();
  SPI.beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE1)); // Ajusta velocidad si es necesario

  attachInterrupt(digitalPinToInterrupt(ADS_DRDY), drdyISR, FALLING);

  // Inicialización
  resetADS();
  delay(100);
  configureADS();
  delay(100);

  // Comienza adquisición
  digitalWrite(ADS_START, HIGH);
  sendCommand(0x10); // RDATAC (Read Data Continuous Mode)
}

void loop() {
  if (dataReady) {
    dataReady = false;
    digitalWrite(ADS_CS, LOW);
    
    // Lectura: 3 bytes estado + 6 * 3 bytes canales
    byte buffer[3 + NUM_CHANNELS * 3];
    for (int i = 0; i < sizeof(buffer); i++) {
      buffer[i] = SPI.transfer(0x00);
    }

    digitalWrite(ADS_CS, HIGH);

    // Parsear y mostrar datos
    Serial.print("Canales: ");
    for (int i = 0; i < NUM_CHANNELS; i++) {
      long value = ((long)buffer[3 + i * 3] << 16) |
                   ((long)buffer[3 + i * 3 + 1] << 8) |
                   (long)buffer[3 + i * 3 + 2];
      // Conversión a signed 24 bits
      if (value & 0x800000) value |= 0xFF000000;
      Serial.print(value);
      Serial.print(" ");
    }
    Serial.println();
  }
}

void resetADS() {
  digitalWrite(ADS_RESET, LOW);
  delay(10);
  digitalWrite(ADS_RESET, HIGH);
  delay(10);
}

void sendCommand(byte cmd) {
  digitalWrite(ADS_CS, LOW);
  SPI.transfer(cmd);
  digitalWrite(ADS_CS, HIGH);
  delayMicroseconds(3);
}

void writeRegister(byte reg, byte value) {
  digitalWrite(ADS_CS, LOW);
  SPI.transfer(0x40 | reg); // WREG command
  SPI.transfer(0x00);       // write one register
  SPI.transfer(value);
  digitalWrite(ADS_CS, HIGH);
  delayMicroseconds(3);
}

void configureADS() {
  sendCommand(0x11); // SDATAC: stop continuous mode before config

  // Ejemplo: CONFIG1 = 0x96 (internal clock, 250 SPS, can cambiar)
  writeRegister(0x01, 0x96); // CONFIG1
  writeRegister(0x02, 0xD0); // CONFIG2: test signal off, bias enabled
  writeRegister(0x03, 0xE0); // CONFIG3: reference buffer enabled

  // Habilitar canales 1-6
  for (int i = 0; i < NUM_CHANNELS; i++) {
    writeRegister(0x05 + i, 0x00); // CHnSET: normal electrode input
  }
}
