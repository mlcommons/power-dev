# Client server for PTD (brief description.)


## Building
```bash
#client building
g++ clientServerParserLib.cpp clientConfigParser.cpp maxAmpsVoltsParser.cpp client.cpp -o client
#server building
g++ clientServerParserLib.cpp serverConfigParser.cpp server.cpp -o server.exe -lws2_32 -mwin32

```

## Usage

```bash
#client
./client -i 192.168.104.169 -c clientConfig.json
#server
.\server_v2.exe -i 192.168.104.169 -c .\serverConfig.json

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
