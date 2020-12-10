# Client server for PTD (brief description.)
## Dependencies
Windos OS: install w32tm.
Linux OS: install ntpdate.

Service and client is running as root, because they are using ntp server. If command for ntp in json config is empty, client and server program will assume that ntp server is configured. 

## Building
```bash
#client building (Ubuntu 18.04)
cd ./client_server/client
cmake ./CMakeLists.txt
make
#server building (Windows 10)
cd ./client_server/server
cmake ./CMakeLists.txt
make
```

## Usage

```bash
#client
./client -i 192.168.104.169 -c clientConfig.json
#server
.\server.exe -i 192.168.104.169 -c .\serverConfig.json

```
## Example of configuration file for client.
```json
{
	"ntpStartCommand": "sudo /usr/sbin/ntpdate time.windows.com",
	"testCommands": ["sudo dd if=/dev/sda of=/tmp/tt.dd bs=1M count=3500",
                     "sudo 7zr a -t7z  -mx=9 -m0=LZMA2 -mmt8 /tmp/dd1.7z /tmp/tt.dd"],
    "parserCommand": "python3.8 parse_mlperf.py -pli logs.txt -lgi ./build",
    "correctionFactor": 1.0,
    "maxAmpsVoltsFilePath": "maxValues.txt",
    "logFile": "logs.txt"
}

```
## Example of configuration file for server.
```json
{
  "ntpStartCommand": "w32tm.exe /resync",
  "ptdPath": "D:\\work\\spec_ptd-main\\PTD\\ptd-windows-x86.exe",
  "serialNumber": "C2PH13047V",
  "ptdFlags": {
    "port": 8888,
    "quietMode": false,
    "increaseGeneralDebugOutput": false,
    "increaseMeterSpecificDebugOutput": false,
    "logfile": "D:\\work\\c\\logs_ptdeamon.txt",
    "extendedLogFileFormat": true,
    "debugOutputToFile": "",
    "temperatureMode": false,
    "voltageAutoRange": "",
    "ampereAutoRange": "",
    "baudRate": false,
    "enableDcMeasurements": false,
    "channelNumber": false,
    "GpibInterface": false,
    "GpibBoardNumber": false,
    "useYokogawaUsbOrEthernetInterface": 49
  }
}

```
