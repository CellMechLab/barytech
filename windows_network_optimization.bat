@echo off
echo ========================================
echo Windows Network Optimization for MQTT
echo ========================================
echo.

echo [1/6] Checking current TCP settings...
netsh interface tcp show global
echo.

echo [2/6] Optimizing TCP settings for high performance...
netsh int tcp set global autotuninglevel=normal
netsh int tcp set global chimney=enabled
netsh int tcp set global dca=enabled
netsh int tcp set global netdma=enabled
netsh int tcp set global ecncapability=enabled
netsh int tcp set global timestamps=disabled
netsh int tcp set global initialRto=2000
netsh int tcp set global rss=enabled
netsh int tcp set global maxsynretransmissions=2
netsh int tcp set global fastopen=enabled
netsh int tcp set global pacingprofile=lowlatency
echo.

echo [3/6] Setting registry optimizations...
reg add "HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" /v "TcpTimedWaitDelay" /t REG_DWORD /d 30 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" /v "MaxUserPort" /t REG_DWORD /d 65534 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" /v "MaxFreeTcbs" /t REG_DWORD /d 65536 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" /v "MaxHashTableSize" /t REG_DWORD /d 65536 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" /v "TcpMaxDupAcks" /t REG_DWORD /d 2 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" /v "Tcp1323Opts" /t REG_DWORD /d 1 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" /v "TcpWindowSize" /t REG_DWORD /d 65535 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" /v "GlobalMaxTcpWindowSize" /t REG_DWORD /d 65535 /f
echo.

echo [4/6] Optimizing network adapter settings...
for /f "tokens=*" %%i in ('netsh interface show interface ^| findstr "Enabled"') do (
    for /f "tokens=1,2" %%a in ("%%i") do (
        echo Optimizing adapter: %%b
        netsh interface set interface "%%b" mtu=1500
    )
)
echo.

echo [5/6] Setting power plan to high performance...
powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c
echo.

echo [6/6] Final TCP settings check...
netsh interface tcp show global
echo.

echo ========================================
echo Optimization Complete!
echo ========================================
echo.
echo These optimizations should improve MQTT performance:
echo - Increased TCP window sizes
echo - Optimized TCP parameters for high throughput
echo - Reduced connection timeouts
echo - Enabled TCP optimizations
echo - Set high-performance power plan
echo.
echo Restart your MQTT applications for best results.
echo.
pause
