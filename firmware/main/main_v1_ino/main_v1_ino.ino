#include <Arduino.h>
#include <IntervalTimer.h>

// ======================== CONFIGURACIÓN ========================
#define SAMPLE_RATE_HZ   20000                 // 5 kS/s
#define TABLE_SIZE       1024                 // LUT seno
#define USE_EXTENDED_FRAME 1                  // 0 = compacto (17 B), 1 = extendido (23 B)
#define SERIAL_BAUD      1000000              // se ignora en USB CDC, útil en UART

// Frecuencias de prueba (todas < Nyquist = 2.5 kHz)
static const float FREQ_ADC24 = 1000.0f;      // seno 24 bits
static const float FREQ_16B[6] = { 600.0f, 700.0f, 300.0f, 400.0f, 800.0f, 500.0f };
// Amplitudes (ajusta a gusto)
static const int32_t AMP_24B = 12000; // pico ~2^22 - 1 para 24b signed
static const int16_t AMP_16B = 12000;         // pico para 16b (evita saturar)

// Tamaño de frame
#if USE_EXTENDED_FRAME
  static const uint32_t FRAME_BYTES = 23;
#else
  static const uint32_t FRAME_BYTES = 17;
#endif

// Buffer circular de tramas (SPSC)
#define TX_QUEUE_LEN 2048
volatile uint32_t drop_count = 0;
volatile uint16_t q_write = 0;
volatile uint16_t q_read  = 0;
uint8_t tx_queue[TX_QUEUE_LEN][FRAME_BYTES];

// ====================== GENERADOR DE SENO ======================
static float sine_table[TABLE_SIZE];

// Fases [0, TABLE_SIZE)
static float ph_adc24 = 0.0f;
static float ph_16b[6] = {0};

static float step_adc24;
static float step_16b[6];

IntervalTimer sampler;
volatile uint32_t sample_id = 0;

// ====================== CRC16 (para extendido) =================
static uint16_t crc16_ccitt(const uint8_t* data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= (uint16_t)data[i] << 8;
    for (int j = 0; j < 8; j++) {
      if (crc & 0x8000) crc = (crc << 1) ^ 0x1021;
      else              crc = (crc << 1);
    }
  }
  return crc;
}

// ====================== EMPAQUE 24-bit LE ======================
static inline void pack_s24_le(int32_t val, uint8_t* out) {
  // saturar a 24 bits signed
  if (val >  0x7FFFFF) val =  0x7FFFFF;
  if (val < -0x800000) val = -0x800000;
  // little-endian 24b (2's complement)
  out[0] = (uint8_t)(val & 0xFF);
  out[1] = (uint8_t)((val >> 8) & 0xFF);
  out[2] = (uint8_t)((val >> 16) & 0xFF);
}

// ====================== ISR: PRODUCE UNA TRAMA =================
void isr_sample() {
  uint16_t next_w = (q_write + 1) & (TX_QUEUE_LEN - 1);
  if (next_w == q_read) { drop_count++; return; }

  uint8_t* frame = tx_queue[q_write];
  uint32_t off = 0;

  frame[0] = 0xA5; frame[1] = 0x5A; off = 2;

#if USE_EXTENDED_FRAME
  uint32_t sid = sample_id;
  frame[off+0] = (uint8_t)(sid & 0xFF);
  frame[off+1] = (uint8_t)((sid >> 8) & 0xFF);
  frame[off+2] = (uint8_t)((sid >> 16) & 0xFF);
  frame[off+3] = (uint8_t)((sid >> 24) & 0xFF);
  off += 4;
#endif

  int32_t s24 = (int32_t)lrintf(AMP_24B * sine_table[(int)ph_adc24]);
  pack_s24_le(s24, &frame[off]); off += 3;

  for (int k = 0; k < 6; ++k) {
    int16_t s16 = (int16_t)lrintf(AMP_16B * sine_table[(int)ph_16b[k]]);
    frame[off+0] = (uint8_t)(s16 & 0xFF);
    frame[off+1] = (uint8_t)((s16 >> 8) & 0xFF);
    off += 2;
    ph_16b[k] += step_16b[k];
    if (ph_16b[k] >= TABLE_SIZE) ph_16b[k] -= TABLE_SIZE;
  }

#if USE_EXTENDED_FRAME
  uint16_t crc = crc16_ccitt(frame, off);
  frame[off+0] = (uint8_t)(crc >> 8);
  frame[off+1] = (uint8_t)(crc & 0xFF);
  off += 2;
#endif

  ph_adc24 += step_adc24;
  if (ph_adc24 >= TABLE_SIZE) ph_adc24 -= TABLE_SIZE;

  q_write = next_w;        // publicar frame
  sample_id++;
}

// ============================ SETUP ============================
void setup() {
  // Serial: si es USB CDC, el baud es ignorado (OK); si usas UART, útil tener 1e6.
  Serial.begin(SERIAL_BAUD);
  while (!Serial && millis() < 2000) { /* espera breve */ }

  // LUT de seno
  for (int i = 0; i < TABLE_SIZE; ++i) {
    float ang = (2.0f * PI * i) / (float)TABLE_SIZE;
    sine_table[i] = sinf(ang);
  }

  // Pasos de fase
  step_adc24 = (FREQ_ADC24 / (float)SAMPLE_RATE_HZ) * TABLE_SIZE;
  for (int k = 0; k < 6; ++k) {
    step_16b[k] = (FREQ_16B[k] / (float)SAMPLE_RATE_HZ) * TABLE_SIZE;
  }

  // Timer a 5 kHz
  sampler.begin(isr_sample, 1000000.0f / SAMPLE_RATE_HZ);
  sampler.priority(32);   // 0 (altísima) .. 255 (baja). 32 es muy alta sin ser extrema.

}

// ============================= LOOP ============================
void loop() {
 const int MAX_FRAMES_PER_ITER = 32;   // lote pequeño para evitar monopolizar CPU
  int written_frames = 0;

  while (q_read != q_write && written_frames < MAX_FRAMES_PER_ITER) {
    int avail = Serial.availableForWrite();
    if (avail < (int)FRAME_BYTES) {
      break; // no hay espacio para un frame completo; salimos
    }
    // escribir exactamente un frame
    Serial.write(tx_queue[q_read], FRAME_BYTES);
    q_read = (q_read + 1) & (TX_QUEUE_LEN - 1);
    written_frames++;
  }

  // opcional: pequeño yield para dar chance al stack USB
  // (en Teensy 4.x no es crítico, pero ayuda)
  yield();

}
