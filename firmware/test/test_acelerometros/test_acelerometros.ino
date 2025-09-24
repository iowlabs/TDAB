#include <MPU9250_asukiaaa.h>
#include <ArduinoJson.h>

#define MPU9250_ADDRESS 0x68
#define SMPLRT_DIV      0x19
#define CONFIG          0x1A
#define GYRO_CONFIG     0x1B
#define ACCEL_CONFIG    0x1C

MPU9250_asukiaaa mySensor;

unsigned long lastMicros = 0;
const unsigned long intervalMicros = 100;  // 1000 Hz

void configureMPU9250() {
  Wire.beginTransmission(MPU9250_ADDRESS);
  Wire.write(SMPLRT_DIV);
  Wire.write(0x00);  // Sample Rate Divider = 0 => Fs = 1kHz
  Wire.endTransmission();

  Wire.beginTransmission(MPU9250_ADDRESS);
  Wire.write(CONFIG);
  Wire.write(0x00);  // DLPF_CFG = 0 (max bandwidth)
  Wire.endTransmission();

  Wire.beginTransmission(MPU9250_ADDRESS);
  Wire.write(GYRO_CONFIG);
  Wire.write(0x00);  // ±250°/s
  Wire.endTransmission();

  Wire.beginTransmission(MPU9250_ADDRESS);
  Wire.write(ACCEL_CONFIG);
  Wire.write(0x00);  // ±2g
  Wire.endTransmission();
}


void setup() {
  Serial.begin(500000);  // Asegúrate de usar la misma velocidad en el monitor serial
  while (!Serial);

  // Iniciar I2C1 en los pines 17 (SDA1) y 16 (SCL1)
  Wire1.begin();                  
  Wire1.setClock(1000000);       // Opcional: velocidad I2C 1 MHz (si la IMU lo soporta)

  mySensor.setWire(&Wire1);      // Usar Wire1 en lugar del Wire por defecto (I2C0)
  mySensor.beginAccel();
  mySensor.beginGyro();
  configureMPU9250();  
  //mySensor.beginMag();           // Para MPU9250


  Serial.println("IMU inicializada en I2C1");
}

void loop() {
  if (micros() - lastMicros >= intervalMicros) {
    lastMicros += intervalMicros;

    mySensor.accelUpdate();
    mySensor.gyroUpdate();

    float ax = mySensor.accelX();
    float ay = mySensor.accelY();
    float az = mySensor.accelZ();

    float gx = mySensor.gyroX();
    float gy = mySensor.gyroY();
    float gz = mySensor.gyroZ();

   // Crear JSON
    StaticJsonDocument<256> doc;

    doc["time"] = millis();
    JsonObject accel = doc.createNestedObject("acc");
    accel["x"] = ax;
    accel["y"] = ay;
    accel["z"] = az;

    JsonObject gyro = doc.createNestedObject("gyro");
    gyro["x"] = gx;
    gyro["y"] = gy;
    gyro["z"] = gz;

    serializeJson(doc, Serial);
    Serial.println();
  }
}
