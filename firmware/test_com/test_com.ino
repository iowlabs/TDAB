#include <Arduino.h>

#define SAMPLE_RATE 5000
#define TABLE_SIZE 100
#define END_MARKER 0xFF  // marcador de fin de paquete

int16_t sine2k_1[TABLE_SIZE];
int16_t sine2k_2[TABLE_SIZE];
int16_t sine2k_3[TABLE_SIZE];
int16_t sine1k_1[TABLE_SIZE];
int16_t sine1k_2[TABLE_SIZE];
int16_t sine1k_3[TABLE_SIZE];

volatile uint16_t indx = 0;
IntervalTimer timer;

void setup() {
  Serial.begin(1000000);
  while (!Serial);

  // generar tablas de seno
  for (int i = 0; i < TABLE_SIZE; i++) {
    sine2k_1[i] = 1000 * sin(2 * PI * i / TABLE_SIZE); // 2kHz
    sine2k_2[i] = 1000 * sin(2 * PI * i / TABLE_SIZE + PI / 3);
    sine2k_3[i] = 1000 * sin(2 * PI * i / TABLE_SIZE + 2 * PI / 3);
    sine1k_1[i] = 1000 * sin(2 * PI * i / (TABLE_SIZE * 2)); // 1kHz (doble periodo)
    sine1k_2[i] = 1000 * sin(2 * PI * i / (TABLE_SIZE * 2) + PI / 3);
    sine1k_3[i] = 1000 * sin(2 * PI * i / (TABLE_SIZE * 2) + 2 * PI / 3);
  }

  timer.begin(sendData, 1000000 / SAMPLE_RATE);  // llama cada 200 µs
}

void sendData() {
  uint8_t buffer[13];  // 6x int16 (12 bytes) + 1 byte end marker

  // índices
  int i2k = indx % TABLE_SIZE;
  int i1k = indx % (TABLE_SIZE * 2);

  memcpy(buffer, &sine2k_1[i2k], 2);
  memcpy(buffer + 2, &sine2k_2[i2k], 2);
  memcpy(buffer + 4, &sine2k_3[i2k], 2);
  memcpy(buffer + 6, &sine1k_1[i1k], 2);
  memcpy(buffer + 8, &sine1k_2[i1k], 2);
  memcpy(buffer + 10, &sine1k_3[i1k], 2);

  buffer[12] = END_MARKER;  // marcador de fin

  Serial.write(buffer, sizeof(buffer));

  indx++;
}

void loop(){}