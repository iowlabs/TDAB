#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>


#define TEST 1

// Crear el objeto del sensor
Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);
float x,y,z;
float roll,pitch;
float rollF,pitchF;

int cont1 = 0;
int cont2 = 10;
int cont3 = 20;
int cont4 = 30;
int cont5 = 40;
int cont6 = 50;


// Variables para el temporizador
unsigned long previousMicros = 0;
const unsigned long intervalMicros = 1000; // 1000 µs = 1 ms = 1000 Hz

void setup()
{
  // Configuración de Serial
  Serial.begin(500000);
  while (!Serial) delay(10);

  // Inicializar el ADXL345
  if (!accel.begin()) 
  {
    Serial.println("No se pudo inicializar el ADXL345.");
    //while (1);
  }
  Serial.println("Inicializado programa");

  // Configurar el rango y la tasa de salida de datos (ODR)
  //accel.setRange(ADXL345_RANGE_2_G); // Rango ±2G (puedes cambiar a ±4G o ±8G)
  //setDataRate(ADXL345_DATARATE_800_HZ); // ODR más cercano a 1000 Hz

  // Nota: El ODR máximo del ADXL345 es 3200 Hz
}

void loop() 
{
  
  unsigned long currentMicros = micros();

  // Verificar si es tiempo de leer y enviar datos
  if (currentMicros - previousMicros >= intervalMicros) 
  {
    previousMicros = currentMicros;
    if( TEST == 0 )
    {
      // Leer datos del acelerómetro
      sensors_event_t event;
      accel.getEvent(&event);
      // Enviar datos por Serial
      /*
      Serial.print("Aceleración: ");
      Serial.print(event.acceleration.x, 3); Serial.print(", ");
      Serial.print(event.acceleration.y, 3); Serial.print(", ");
      Serial.print(event.acceleration.z, 3); Serial.println(" m/s^2");
      */
      x = event.acceleration.x;
      y = event.acceleration.y;
      z = event.acceleration.z;
      roll = atan(y/sqrt(pow(x,2)+pow(z,2)))*180/PI;
      pitch = atan(-1*x/sqrt(pow(y,2)+pow(z,2)))*180/PI;
      rollF = 0.94*rollF + 0.06*roll;
      pitchF = 0.94 * rollF + 0.06 * pitch;
      Serial.print(rollF);
      Serial.print("/");
      Serial.println(pitchF); 
    } 
    else
    {
      cont1+=1;
      cont2+=1;
      cont3+=1;
      cont4+=1;
      cont5+=1;
      cont6+=1;

      if(cont1 >=1000){cont1 = 0;}
      if(cont2 >=1000){cont2 = 0;}
      if(cont3 >=1000){cont3 = 0;}
      if(cont4 >=1000){cont4 = 0;}
      if(cont5 >=1000){cont5 = 0;}
      if(cont6 >=1000){cont6 = 0;}

      Serial.print(cont1);Serial.print(",");
      Serial.print(cont2);Serial.print(",");
      Serial.print(cont3);Serial.print(",");
      Serial.print(cont4);Serial.print(",");
      Serial.print(cont5);Serial.print(",");
      Serial.print(cont6);Serial.println("");
    }
  }
}

// Función para configurar la tasa de salida de datos (ODR)
void setDataRate(uint8_t dataRate) 
{
  Wire.beginTransmission(0x53); // Dirección I2C del ADXL345
  Wire.write(0x2C);             // Registro BW_RATE
  Wire.write(dataRate);         // Configurar la tasa de datos
  Wire.endTransmission();
}
