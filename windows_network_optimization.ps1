# Windows Network Optimization for High-Performance MQTT
# Run as Administrator

Write-Host "========================================" -ForegroundColor Green
Write-Host "Windows Network Optimization for MQTT" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Check if running as Administrator
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "This script requires Administrator privileges!" -ForegroundColor Red
    Write-Host "Please run PowerShell as Administrator and try again." -ForegroundColor Red
    exit
}

Write-Host "[1/8] Checking current TCP settings..." -ForegroundColor Yellow
netsh interface tcp show global
Write-Host ""

Write-Host "[2/8] Optimizing TCP settings for high performance..." -ForegroundColor Yellow
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
Write-Host ""

Write-Host "[3/8] Setting registry optimizations..." -ForegroundColor Yellow
$regPath = "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"

# TCP/IP Registry Optimizations
$regSettings = @{
    "TcpTimedWaitDelay" = 30
    "MaxUserPort" = 65534
    "MaxFreeTcbs" = 65536
    "MaxHashTableSize" = 65536
    "TcpMaxDupAcks" = 2
    "Tcp1323Opts" = 1
    "TcpWindowSize" = 65535
    "GlobalMaxTcpWindowSize" = 65535
    "TcpMaxDataRetransmissions" = 5
    "TcpMaxConnectRetransmissions" = 2
    "TcpInitialRtt" = 2000
    "TcpMaxDupAcks" = 2
    "TcpTimedWaitDelay" = 30
    "MaxUserPort" = 65534
    "MaxFreeTcbs" = 65536
    "MaxHashTableSize" = 65536
}

foreach ($setting in $regSettings.GetEnumerator()) {
    Set-ItemProperty -Path $regPath -Name $setting.Key -Value $setting.Value -Type DWord -Force
    Write-Host "Set $($setting.Key) = $($setting.Value)"
}
Write-Host ""

Write-Host "[4/8] Optimizing network adapter settings..." -ForegroundColor Yellow
$adapters = Get-NetAdapter | Where-Object { $_.Status -eq "Up" }
foreach ($adapter in $adapters) {
    Write-Host "Optimizing adapter: $($adapter.Name)"
    Set-NetAdapterAdvancedProperty -Name $adapter.Name -RegistryKeyword "*FlowControl" -RegistryValue 0
    Set-NetAdapterAdvancedProperty -Name $adapter.Name -RegistryKeyword "*InterruptModeration" -RegistryValue 0
    Set-NetAdapterAdvancedProperty -Name $adapter.Name -RegistryKeyword "*JumboPacket" -RegistryValue 1514
}
Write-Host ""

Write-Host "[5/8] Setting power plan to high performance..." -ForegroundColor Yellow
powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c
Write-Host ""

Write-Host "[6/8] Optimizing system memory settings..." -ForegroundColor Yellow
# Disable paging executive
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management" -Name "DisablePagingExecutive" -Value 1 -Type DWord

# Large system cache
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management" -Name "LargeSystemCache" -Value 0 -Type DWord

# System cache limit
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management" -Name "SystemCacheLimit" -Value 0 -Type DWord
Write-Host ""

Write-Host "[7/8] Optimizing network interface settings..." -ForegroundColor Yellow
# Increase network buffer sizes
$nicSettings = @{
    "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\*" = @{
        "TcpWindowSize" = 65535
        "Tcp1323Opts" = 1
    }
}

foreach ($path in $nicSettings.Keys) {
    $interfaces = Get-ChildItem -Path $path -ErrorAction SilentlyContinue
    foreach ($interface in $interfaces) {
        foreach ($setting in $nicSettings[$path].GetEnumerator()) {
            Set-ItemProperty -Path $interface.PSPath -Name $setting.Key -Value $setting.Value -Type DWord -Force -ErrorAction SilentlyContinue
        }
    }
}
Write-Host ""

Write-Host "[8/8] Final TCP settings check..." -ForegroundColor Yellow
netsh interface tcp show global
Write-Host ""

Write-Host "========================================" -ForegroundColor Green
Write-Host "Optimization Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "These optimizations should improve MQTT performance:" -ForegroundColor Cyan
Write-Host "- Increased TCP window sizes" -ForegroundColor White
Write-Host "- Optimized TCP parameters for high throughput" -ForegroundColor White
Write-Host "- Reduced connection timeouts" -ForegroundColor White
Write-Host "- Enabled TCP optimizations" -ForegroundColor White
Write-Host "- Set high-performance power plan" -ForegroundColor White
Write-Host "- Optimized network adapter settings" -ForegroundColor White
Write-Host "- Optimized memory management" -ForegroundColor White
Write-Host ""
Write-Host "Restart your MQTT applications for best results." -ForegroundColor Yellow
Write-Host ""
Write-Host "Press any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
