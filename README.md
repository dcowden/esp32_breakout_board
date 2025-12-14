# esp32 breakout boards

These are for  this board:

https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/_images/esp32_devkitC_v4_pinlayout.png


## Included boards
 1. **esp32_breakout_smt**  A board designed to expose the stuff i need for xcc tracker, all on one board, with smt style mounts
 2. **esp32_breakout_tht** Through hole version of the above ( again designed for the xc case in mind
 3. **esp32_breakout_tht2** A simple board designed to just break out pins-- and then extned through a shield approach
 4. **esp32_breakout_tht2_shield** A shield for the agove that adds the stuff needed for xc application
 
## The stuff that the XC board needs

The xc board logs data from an nrf52840 and sends it to an esp32 , which processes further. 
The board needs:
   1. esp32 devkit c ( we need all the pins) (38 pin)
   2. seed xiao nrf52840  (14 pin) 
   3. ds3231 (isc) (weird 5 pin thing)
   4. i2c oled 
   5. micro sd card holder ( spi )