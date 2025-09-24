#include "Wire.h"

void TCA9548A(uint8_t bus){
  Wire.beginTransmission(0x70);  // TCA9548A address
  Wire.write(1 << bus);          // send byte to select bus
  Wire.endTransmission();
  Serial.print(bus);
}

void setup() {
  // put your setup code here, to run once:
  Wire.begin();
  
  Serial.begin(500000);
  while (!Serial);   // Wait for Arduino Serial Monitor
  Serial.println(F("\nI2C Scanner"));
  
  Serial.println(F("Scanning Multiplexor..."));
  
  myport.beginTransmission(0x70);
  int error = myport.endTransmission();

  if (error == 0)
  {
    Serial.print(F("Device found at address 0x"));
    if (address < 16) 
    {
        Serial.print("0");
    }
    Serial.print(address,HEX);
  } 
  else if (error==4) 
  {
    Serial.print(F("Unknown error at address 0x"));
    if (address < 16) 
    {
        Serial.print("0");
    }
    Serial.println(address,HEX);
  }
  

  delay(500);




}

void loop() {
  // put your main code here, to run repeatedly:

}
