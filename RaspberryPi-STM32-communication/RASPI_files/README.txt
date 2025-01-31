This python file should be run on the raspberry pi terminal.
This python tests for the handling of data from the ADC to STM32 and then over to the RASPI, with one core acting
as an offline buffer and the other acting as a producer sending data to the broker.
Run this file after flashing the hex code onto the STM32.

NOTE: Ensure RASPI and STM and ADC are connected through spi before testing the system
Please refer to the connections document.