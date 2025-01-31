Open the project folder in STM32CubeIDE for editing the code

For flashing the code onto the stm32, you need to download STM32Programmer
1. Once you have STM32Programmer installed, connect the STM32 board. For this code STM32 NuceloF401RE board was used.
2. On the right corner of the software, there is a drop-down menu, select ST-LINK there
3. Click connect to form communication between your stm and the programmer
4. On the left corner, select Erasing and Programming, which should be the second icon on the sidebar (icon is similar to a download icon)
5. Browse for the hex file and upload it on the software
6. Click start programming
7. The STM LED1 starts blinking, meaning the file is being flashed onto the STM
8. Once its done you should see a message saying Operation Successful. 

