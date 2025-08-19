#include <Wire.h>

#define MUX_ADDR 0x70  // Dirección del TCA9548A
#define POT_ADDR 0x20  // Dirección del AD5122

#define MAX_RESISTANCE_KOHM 10.0  // 10kΩ terminal
#define POT_STEPS 256             // Resolución del potenciómetro






void setup()
{
  Wire.begin();
  Serial.begin(115200);
}

void loop()
{

}



void selectMuxChannel(uint8_t channel) 
{
  if (channel > 7) return;
  Wire.beginTransmission(MUX_ADDR);
  Wire.write(1 << channel);
  Wire.endTransmission();
}


void writeHFPotRegister(uint8_t reg, uint8_t value) 
{
  Wire.beginTransmission(POT_ADDR);
  Wire.write((reg << 2) | 0b00); // Escribir con control bits
  Wire.write(value);
  Wire.endTransmission();
}


/* 
  resistence: resistencia en k ohms
  channel:    canal de filtro
*/
void setPotResistanceHF(uint8_t _channel,  float _resistance) 
{
  // Validaciones
  if (_resistance > MAX_RESISTANCE_KOHM) return;

  // Seleccionar canal del MUX
  selectMuxChannel(_channel);

  // Calcular paso
  uint8_t step = (uint8_t)((_resistance / MAX_RESISTANCE_KOHM) * (POT_STEPS - 1));
  
  //pot channel 0
  uint8_t reg =  0x04;
  writePotRegister(reg, step);
  
  //pot channel 0
  reg = 0x05;
  writePotRegister(reg, step);  
}

