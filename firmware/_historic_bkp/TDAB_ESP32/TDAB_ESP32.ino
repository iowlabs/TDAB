/*
list of cmd
  read:
      {"cmd":"get","arg":{}}
  start continuos data transfer:
      {"cmd":"start","arg":{}}      
  stop continous data transfer:
      {"cmd":"stop","arg":{}}
  enable channel:
      {"cmd":"ench","arg":{"ch":1,"state":1}}
  set bottom fc
      {"cmd":"set_bfc","arg":{"ch":1,"bfc":0.5}}
  set top fc
      {"cmd":"set_tfc","arg":{"ch":1,"tfc":100}}
  set first stage gain
      {"cmd":"set_fsg","arg":{"ch":1,"fsg":10}}
  set main stage gain
      {"cmd":"set_msg","arg":{"ch":1,"msg":2}}
*/

#include <ArduinoJson.h>

#define NSAMPLES 1000
#define ADC_PIN_1 32
#define ADC_PIN_2 33
#define ADC_PIN_3 25
#define ADC_PIN_4 26
#define ADC_PIN_5 27
#define ADC_PIN_6 14

#define IDLE 0
#define RUNNING 1

bool ch1_en = true;
bool ch2_en = true;
bool ch3_en = true;
bool ch4_en = true;
bool ch5_en = true;
bool ch6_en = true;

bool  ch_en [6] = {true,true,true,true,true,true};
float ch_tfc[6] = {100.0,100.0,100.0,100.0,100.0,100.0};
float ch_bfc[6] = {0.5,0.5,0.5,0.5,0.5,0.5};
float ch_fsg[6] = {100.0,100.0,100.0,100.0,100.0,100.0};
float ch_msg[6] = {2.0,2.0,2.0,2.0,2.0,2.0};


uint8_t nch = 0;

unsigned long start_time = 0;
unsigned long stop_time = 0;

const char* cmd;
uint8_t channel = 0;
bool channel_status = false; 

float bfc = 0.0;
float tfc = 0.0;
float fsg = 0.0;
float msg = 0.0;

int modo = IDLE;
int counter = 0;


void processCmd();
void readADC();
void readN(int _num);
void enableChannel(uint8_t _ch, bool _state);
void setFSG(uint8_t _ch, float _fsg);
void setMSG(uint8_t _ch, float _msg);
void setBFC(uint8_t _ch, float _bfc);
void setTFC(uint8_t _ch, float _tfc);

void setup() 
{
  Serial.begin(500000);
}

void loop()
{
  if (Serial.available() > 0)
  {
    processCmd();
  }
  else
  {
    if( modo == RUNNING )
    {
      readADC();
      delay(1);
      //delayMicroseconds(5);
    }
  }
}


void processCmd()
{
  StaticJsonDocument<1024> doc_rx;  
  DeserializationError error_rx;
  //check for error
  error_rx = deserializeJson(doc_rx, Serial);
  if (error_rx)
  {
		Serial.print(F("deserializeJson() failed: "));
	  Serial.println(error_rx.c_str());
  }
  
  //parsing incoming msg
  cmd = doc_rx["cmd"];
  JsonObject arg_js = doc_rx["arg"];

  //prossesing incoming command
  if(strcmp(cmd,"get")==0)
  {   
    //Serial.println("Reading ADC");
    delay(100);
    counter = 0;
    readN(NSAMPLES); 
  }
  else if(strcmp(cmd,"start")==0)
  {   
    counter = 0;
    modo = RUNNING;
  }
  else if(strcmp(cmd,"stop")==0)
  {   
    modo = IDLE;
  }
  else if(strcmp(cmd,"ench")==0)
  {
    Serial.println("Enabling channel");
    channel = arg_js["ch"];
    channel_status = arg_js["state"];
    enableChannel(channel,channel_status);
  }
  else if(strcmp(cmd,"set_bfc")==0)
  {
    Serial.println("Setting  bottom fc");
    channel = arg_js["ch"];
    bfc = arg_js["bfc"];
    setBFC(channel,bfc);
  }
  else if(strcmp(cmd,"set_tfc")==0)
  {
    Serial.println("Setting  top fc");
    channel = arg_js["ch"];
    tfc = arg_js["bfc"];
    setTFC(channel,tfc);
  }
  else if(strcmp(cmd,"set_fsg")==0)
  {
    Serial.println("Setting first stage gain");
    channel = arg_js["ch"];
    fsg = arg_js["fsg"];
    setFSG(channel,fsg);
  }
  else if(strcmp(cmd,"set_msg")==0)
  {
    Serial.println("Setting main stage gain");
    channel = arg_js["ch"];
    msg = arg_js["msg"];
    setMSG(channel,msg);
  }
  
}


void readADC()
{
  if(ch1_en)
  {
    Serial.print(analogRead(ADC_PIN_1));    
  }
  if(ch2_en)
  {
    Serial.print(",");
    Serial.print(analogRead(ADC_PIN_2)); 
  }
  if(ch3_en)
  {
    Serial.print(",");
    Serial.print(analogRead(ADC_PIN_3)); 
  }
  if(ch4_en)
  {
    Serial.print(",");
    Serial.print(analogRead(ADC_PIN_4));
  }
  if(ch5_en)
  {
    Serial.print(",");
    Serial.print(analogRead(ADC_PIN_5));  
  }
  if(ch6_en)
  {
    Serial.print(",");  
    Serial.print(counter);
    counter += 1;
    //Serial.print(analogRead(ADC_PIN_6));
  }
  Serial.println("");
  
}


void readN(int _num)
{ 
  for(int i = 0; i < NSAMPLES; i++)
  {
    readADC();
  }
}

void enableChannel(uint8_t _ch, bool _state)
{
  ch_en[_ch] = _state;
  Serial.print("Channels: ");
  for(int i = 0; i < 6; i++)
  {
    Serial.print(ch_en[i]);
    Serial.print(" ");
  }
  Serial.println("");
}

void setBFC(uint8_t _ch, float _bfc)
{
  ch_bfc[_ch] = _bfc;
  Serial.print("Setting bottom fc from channel ");
  Serial.print(_ch);
  Serial.print(" to ");
  Serial.println(_bfc);
}

void setTFC(uint8_t _ch, float _tfc)
{
  ch_tfc[_ch] = _tfc;
  Serial.print("Setting top fc from channel ");
  Serial.print(_ch);
  Serial.print(" to ");
  Serial.println(_tfc);
}

void setMSG(uint8_t _ch, float _msg)
{
  ch_msg[_ch] = _msg;
  Serial.print("Setting main stage gain from channel ");
  Serial.print(_ch);
  Serial.print(" to ");
  Serial.println(_msg);
}

void setFSG(uint8_t _ch, float _fsg)
{
  ch_fsg[_ch] = _fsg;
  Serial.print("Setting fist stage gain from channel ");
  Serial.print(_ch);
  Serial.print(" to ");
  Serial.println(_fsg);
}