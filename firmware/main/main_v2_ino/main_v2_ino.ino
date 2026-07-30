#include <Arduino.h>
#include <Wire.h>
#include <IntervalTimer.h>
#include <ArduinoJson.h>
#include <MPU9250_WE.h>


// ======================== CONFIGURACIÓN ========================
#define SAMPLE_RATE_HZ   5000                 // 5 kS/s
#define TABLE_SIZE       1024                 // LUT seno
#define USE_EXTENDED_FRAME 1                  // 0 = compacto (17 B), 1 = extendido (23 B)
#define SERIAL_BAUD      1000000              // se ignora en USB CDC, útil en UART

// Conteos
#define NUM_ADC24  6   // <-- 6 canales ADC de 24 bits
#define NUM_ACC16  6   // 2 IMUs * 3 ejes = 6


// Tamaño frame extendido: 2 + 4 + 6*3 + 6*2 + 2 = 38
#if USE_EXTENDED_FRAME
  #define FRAME_BYTES (2 + 4 + NUM_ADC24*3 + NUM_ACC16*2 + 2)
#else
  #error "Este sketch usa sólo el formato extendido con CRC"
#endif



// Frecuencias de prueba (todas < Nyquist = 2.5 kHz)
static float freq_adc24[NUM_ADC24] = {500, 500, 500, 100, 100, 100};
static float freq_acc16[NUM_ACC16]= { 300.0f, 250.0f, 100.0f, 50.0f, 10.0f, 5.0f };

// Amplitudes (ajusta a gusto)
static const int32_t AMP_24B = 12000; // pico ~2^22 - 1 para 24b signed
static const int16_t AMP_16B = 12000;         // pico para 16b (evita saturar)



// Buffer circular de tramas (SPSC)
#define TX_QUEUE_LEN 2048
static_assert((TX_QUEUE_LEN & (TX_QUEUE_LEN - 1)) == 0, "TX_QUEUE_LEN must be power of two");

// Lote máximo a escribir por iteración (controla monopolio de CPU)
#define MAX_FRAMES_PER_ITER 32



// =================== MPU9250 ====================
MPU9250_WE imu1 = MPU9250_WE(&Wire1,0x68);
MPU9250_WE imu2 = MPU9250_WE(&Wire1,0x69);
bool imu1_ok = false, imu2_ok = false;

// ========================== ESTADOS / CONTROL =======================

enum RunState : uint8_t { IDLE = 0, RUNNING = 1, STOPPED = 2 };
volatile RunState g_state = IDLE;

// Contador de overflows de cola
volatile uint32_t drop_count = 0;

// ======================== GENERADOR SENOIDAL ========================
static float sine_table[TABLE_SIZE];
static float ph_adc24[NUM_ADC24] = {0};
static float ph_acc16[6] = {0};

static float step_adc24[NUM_ADC24];
static float step_acc16[NUM_ACC16];


// ============================ TX QUEUE ==============================
static uint8_t tx_queue[TX_QUEUE_LEN][FRAME_BYTES];
volatile uint16_t q_write = 0;
volatile uint16_t q_read  = 0;


// ========================== TIMER / CONTADORES ======================
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
if (g_state != RUNNING) return;

  uint16_t next_w = (q_write + 1) & (TX_QUEUE_LEN - 1);
  if (next_w == q_read) { drop_count++; return; }

  uint8_t* f = tx_queue[q_write];
  uint32_t off = 0;

  // Header
  f[0] = 0xA5; f[1] = 0x5A; off = 2;

  // sample_id LE
  uint32_t sid = sample_id;
  f[off+0] = (uint8_t)(sid & 0xFF);
  f[off+1] = (uint8_t)((sid>>8) & 0xFF);
  f[off+2] = (uint8_t)((sid>>16) & 0xFF);
  f[off+3] = (uint8_t)((sid>>24) & 0xFF);
  off += 4;

  // 6× ADC24 (s24 LE)
  for (int i=0;i<NUM_ADC24;++i) {
    int32_t s = (int32_t)lrintf(AMP_24B * sine_table[(int)ph_adc24[i]]);
    pack_s24_le(s, &f[off]); off += 3;
  }

  // 6× ACC16 (int16 LE)
  // Leer cada muestra (o cada N si quieres aligerar)
  //if (imu1_ok && (sample_id % 5 == 0)) imu1.readSensor();
  //if (imu2_ok && (sample_id % 5 == 0)) imu2.readSensor();

  for (int i=0;i<NUM_ACC16;i++) {
    int16_t s = 0;

    if (imu1_ok && i < 3) {
      auto g=imu1.getGValues();
      if (i==0) s = (int16_t)(g.x*10000);
      if (i==1) s = (int16_t)(g.y*10000);
      if (i==2) s = (int16_t)(g.z*10000);
    }
    else if (imu2_ok && i >=3 && i<6) {
      auto g=imu2.getGValues();
      if (i==3) s = (int16_t)(g.x*10000);
      if (i==4) s = (int16_t)(g.y*10000);
      if (i==5) s = (int16_t)(g.z*10000);
    }
    else {
      // Dummy
      s = (int16_t)lrintf(AMP_16B * sine_table[(int)ph_acc16[i]]);
    }

    f[off+0]=(uint8_t)(s & 0xFF);
    f[off+1]=(uint8_t)((s>>8)&0xFF);
    off+=2;
  }

  // CRC16
  uint16_t crc = crc16_ccitt(f, off);
  f[off+0] = (uint8_t)(crc >> 8);
  f[off+1] = (uint8_t)(crc & 0xFF);
  off += 2;

  // Avance de fases
  for (int i=0;i<NUM_ADC24;++i) {
    ph_adc24[i] += step_adc24[i];
    if (ph_adc24[i] >= TABLE_SIZE) ph_adc24[i] -= TABLE_SIZE;
  }
  for (int i=0;i<NUM_ACC16;++i) {
    ph_acc16[i] += step_acc16[i];
    if (ph_acc16[i] >= TABLE_SIZE) ph_acc16[i] -= TABLE_SIZE;
  }

  q_write = next_w;
  sample_id++;
}
// ====================== UTIL: actualizar pasos ======================
static void update_phase_steps() {
  for (int i=0;i<NUM_ADC24;++i)
    step_adc24[i] = (freq_adc24[i] / SAMPLE_RATE_HZ) * TABLE_SIZE;
  for (int i=0;i<NUM_ACC16;++i)
    step_acc16[i] = (freq_acc16[i] / SAMPLE_RATE_HZ) * TABLE_SIZE;
}

// ====================== COMANDOS (JSON por línea) ===================
static char rx_line[256];
static uint16_t rx_len = 0;

static void send_json_reply(const JsonDocument& doc) {
  // Serial.write no-bloqueante (mensaje corto)
  char out[256];
  size_t n = serializeJson(doc, out, sizeof(out));
  if (n > 0 && (int)(n + 1) <= Serial.availableForWrite()) {
    Serial.write((const uint8_t*)out, n);
    Serial.write('\n');
  }
}

static void handle_cmd_line(const char* line) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, line);
  JsonDocument rep;

  if (err) {
    rep["ok"] = false;
    rep["err"] = "bad_json";
    send_json_reply(rep);
    return;
  }

  const char* cmd = doc["cmd"] | "";
  if (strcmp(cmd, "state?") == 0) {
    const char* st = (g_state == RUNNING) ? "RUNNING" : (g_state == IDLE ? "IDLE" : "STOPPED");
    rep["ok"]   = true;
    rep["state"]= st;
    rep["drop"] = (uint32_t)drop_count;
    rep["sid"]  = (uint32_t)sample_id;
    send_json_reply(rep);
    return;
  }

  if (!strcmp(cmd,"start")) {
    if (g_state!=RUNNING) { sample_id=0; drop_count=0; g_state=RUNNING; }
    rep["ok"]=true; rep["state"]="RUNNING"; send_json_reply(rep); return;
  }
  if (!strcmp(cmd,"stop")) {
    g_state=STOPPED; rep["ok"]=true; rep["state"]="STOPPED"; send_json_reply(rep); return;
  }


  // ejemplo "set": {"cmd":"set","arg":{"kind":"adc","ch":0,"freq":750.0}}
  if (!strcmp(cmd,"set")) {
    if (g_state==RUNNING) { rep["ok"]=false; rep["err"]="busy_running"; send_json_reply(rep); return; }
    JsonVariant a=doc["arg"];
    const char* kind = a["kind"] | "";
    int ch = a["ch"] | -1;
    float fq = a["freq"] | NAN;
    bool ok=false;
    if (!strcmp(kind,"adc") && ch>=0 && ch<NUM_ADC24 && isfinite(fq) && fq>=0) {
      freq_adc24[ch]=fq; ok=true;
    } else if (!strcmp(kind,"acc") && ch>=0 && ch<NUM_ACC16 && isfinite(fq) && fq>=0) {
      freq_acc16[ch]=fq; ok=true;
    }
    if (ok){ update_phase_steps(); rep["ok"]=true; } else { rep["ok"]=false; rep["err"]="bad_args"; }
    send_json_reply(rep); return;
  }

  // comando desconocido
  rep["ok"] = false;
  rep["err"] = "unknown_cmd";
  send_json_reply(rep);
}

static void poll_serial_commands()
{
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (rx_len > 0) {
        rx_line[rx_len] = '\0';
        handle_cmd_line(rx_line);
        rx_len = 0;
      }
    } else {
      if (rx_len < sizeof(rx_line) - 1) {
        rx_line[rx_len++] = c;
      } else {
        // overflow: resetea
        rx_len = 0;
      }
    }
  }
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

  update_phase_steps();
 Wire1.begin();
 Wire1.setClock(400000);

  if (imu1.init()) { imu1_ok = true; imu1.autoOffsets(); }
  if (imu2.init()) { imu2_ok = true; imu2.autoOffsets(); }

  Serial.println("starting");

  if (imu1_ok) Serial.println("IMU1 detectada en 0x68");
  if (imu2_ok) Serial.println("IMU2 detectada en 0x69");


  // Timer a 5 kHz
  sampler.begin(isr_sample, 1000000.0f / SAMPLE_RATE_HZ);
  sampler.priority(32);   // 0 (altísima) .. 255 (baja). 32 es muy alta sin ser extrema.

}



// ============================= LOOP ============================
void loop() {
  // 1) comandos JSON
  poll_serial_commands();

  // 2) salida no-bloqueante
  int sent = 0;
  while (q_read != q_write && sent < MAX_FRAMES_PER_ITER) {
    int avail = Serial.availableForWrite();
    if (avail < (int)FRAME_BYTES) {
      break; // no hay espacio para un frame completo; salimos
    }
    // escribir exactamente un frame
    Serial.write(tx_queue[q_read], FRAME_BYTES);
    q_read = (q_read + 1) & (TX_QUEUE_LEN - 1);
    sent++;
  }

  // opcional: pequeño yield para dar chance al stack USB
  // (en Teensy 4.x no es crítico, pero ayuda)
  yield();

}
