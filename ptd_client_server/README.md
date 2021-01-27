## Description

This client-server application is intended to measure the power consumed during the execution of the specified workload.

The purpose of this software is to produce two log files:
* A loadgen log is generated on the SUT by running an inference benchmark.
* A power log is generated on the server by PTDaemon.

The server is intended to be run on the director (the machine on which PTDaemon runs),
and the client is intended to be run on the SUT (system under test).

The client accepts a shell command to run, i.e. the workload.
The power is measured by the server during the command execution on a client.

The command is run twice for each setting: the first time in ranging mode, and the second time is in testing mode.

Client-server sequence diagram: [sequence.png](./doc/sequence.png)

## Prerequisites

* Python 3.7 or newer
* Supported OS: Windows or Linux
* PTDaemon (on the server)
* On Linux: `ntpdate`, optional.
* Assuming you are able to run the required [inference] submission.
  In the README we use [ssd-mobilenet] as an example.

[inference]: https://github.com/mlcommons/inference
[ssd-mobilenet]: https://github.com/mlcommons/inference/tree/master/vision/classification_and_detection

## Installation

`git clone https://github.com/mlcommons/power`

## Configuration

Server required argument:

* `-c FILE` `--configurationFile FILE`

  A server configuration file.

Server optional argument:

* `-h` `--help`
  
  Show help message and exit.

An example of server configuration is provided in the `server.template.conf` file.

Server configuration:

```ini
[server]
# (Optional) NTP server to sync with before each measurement.
# See "NTP Setup" section in the README.md.
#ntpServer: ntp.example.com

# A directory to store output data. A relative or absolute path could be used.
# A new subdirectory will be created per each run.
# The name of this sub-directory consists of date, time, label, and mode (ranging/testing).
# The loadgen log is fetched from the client if the `--send-logs` option is enabled for the client.
# The name of the directory is determined by the workload script running on the SUT, e.g. `ssdmobilenet`.
# The power log, named `spl.txt`, is extracted from the full PTDaemon log (`ptdLogfile`)
outDir: D:\ptd-logs\

# (Optional) IP address and port that server listen on
# Defaults to "0.0.0.0 4950" if not set
#listen: 192.168.1.2 4950


# PTDaemon configuration.
# The following options are mapped to PTDaemon command line arguments.
# Please refer to SPEC PTDaemon Programmers Guide or `ptd -h` for the details.
[ptd]
# A path to PTDaemon executable binary.
ptd: D:\PTD\ptd-windows-x86.exe

# A path to a logfile that PTDaemon produces (`-l` option).
# Note that in the current implementation this file is considered temporary
# and may be overwritten.
logFile: logs_ptdeamon.txt

# (Optional) A port on that PTDaemon listens (`-p` option). Default is 8888.
#networkPort: 8888

# Power Analyzer numerical device type. Refer to `ptd -h` for the full list.
# 49 corresponds to Yokogawa WT310.
deviceType: 49

# interfaceFlag and devicePort describe the physical connection to the analyzer.
# interfaceFlag is either one of -n, -g, -y, -U, or empty.
# Refer to SPEC PTDaemon Programmers Guide or `ptd -h` for the details.
# Below are some examples of interfaceFlag and devicePort pairs.

# Use RS232 interface.
# Empty interfaceFlag corresponds to RS232.
interfaceFlag:
devicePort: COM1

# Use TCPIPv4 ethernet interface.
#interfaceFlag: -n
#devicePort: 192.168.1.123

# Use Yokogawa TMCTL for USB or ethernet interface.
# devicePort should be either the IP address or device serial number.
#interfaceFlag: -y
#devicePort: C2PH13047V

# (Optional) Channel number for multichannel analyzers operating in single channel mode.(`-c ` option)
#channel: 1
```
Client configuration arguments.

Required arguments:

  * `-a ADDR`, `--addr ADDR` 

    A server address.

  * `-w CMD`, `--run-workload CMD`

    A shell command to run under power measurement

  * `-L INDIR`, `--loadgen-logs INDIR`

    A directory to get loadgen logs from.
    The workload command should place inside this directory.

  * `-o OUTDIR`, `--output OUTDIR`

    An output directory to put loadgen logs.
   
Optional arguments:

  * `-h`, `--help`

    Show help message and exit.

  * `-p PORT`, `--port PORT`

    A server port, defaults to 4950.

  * `-n ADDR`, `--ntp ADDR`

     NTP server address, optional

  * `-l "mylabel"`, `--label "mylabel"`

    A human-readable label. Empty string by default.
    The label is used later at the server to distinguish between log directories.

  * `-s`, `--send-logs`

    If enabled, then the loadgen log will be sent to the server and stored alongside the power log.

  * `-f`, `--force`

    Force remove loadgen logs directory from INDIR.

  * `-S`, `--stop-server`

    Stop the server after processing this client.

## Usage example: dummy.sh

Start a server (on a director):
```
./server.py -c server-config.conf
```
Create script `dummy.sh` in `ptd_client_server` directory (on a SUT):
```
#!/bin/bash
#dummy.sh example

sleep 5
if [ ! -e logs ]; then mkdir logs; fi;

# Create empty files with the same names as loadgen

touch logs/mlperf_log_accuracy.json
touch logs/mlperf_log_detail.txt
touch logs/mlperf_log_summary.txt
touch logs/mlperf_log_trace.json
```
```
chmod 775 dummy.sh
```
Then start a client (on the SUT), assuming the director ip address is `192.168.1.2`.
The output would be located at `client-output-directory`.
The script `./dummy.sh` will be used as a workload being measured.
```
./client.py -a 192.168.1.2 -o client-output-directory -w "./dummy.sh" -L loadgen-logs -l "example" -s -n fi.pool.ntp.org
```
### Result

After a successful run, you'll see these new files and directories on the server:
```
D:\ptd-logs
├── … (old entries skipped)
├── 2020-12-28_15-20-52_exmple_ranging
│   ├── spl.txt                           ← power log
│   ├── mlperf_log_accuracy.json        ┐
│   ├── mlperf_log_detail.txt           │ ← loadgen log (if --send-logs is used)
│   ├── mlperf_log_summary.txt          │
│   └── mlperf_log_trace.json           ┘
└── 2020-12-28_15-20-52_example_testing
    ├── spl.txt                           ← power log
    ├── mlperf_log_accuracy.json        ┐
    ├── mlperf_log_detail.txt           │ ← loadgen log (if --send-logs is used)
    ├── mlperf_log_summary.txt          │
    └── mlperf_log_trace.json           ┘
```
And these on the client:
```
client-output-directory
├── … (old entries skipped)
├── 2020-12-28_15-20-52_example_ranging
│   ├── mlperf_log_accuracy.json
│   ├── mlperf_log_detail.txt
│   ├── mlperf_log_summary.txt
│   └── mlperf_log_trace.json
└── 2020-12-28_15-20-52_example_testing
    ├── mlperf_log_accuracy.json
    ├── mlperf_log_detail.txt
    ├── mlperf_log_summary.txt
    └── mlperf_log_trace.json
```

spl.txt consists of the following lines:
```
Time,28-12-2020 15:20:14.682,Watts,22.950000,Volts,228.570000,Amps,0.206430,PF,0.486400,Mark,2021-01-27_20-40-33_example_testing
Time,28-12-2020 15:20:15.686,Watts,23.080000,Volts,228.440000,Amps,0.207320,PF,0.487400,Mark,2021-01-27_20-40-33_example_testing
Time,28-12-2020 15:20:16.691,Watts,22.990000,Volts,228.520000,Amps,0.206740,PF,0.486500,Mark,2021-01-27_20-40-33_example_testing
```

## Usage example: loadgen

Start a server (on a director):
```
./server.py -c server-config.conf
```
There are steps on a SUT:

Clone [inference] into home directory.
Change directory to `~/inference-master/loadgen/benchmark`
```
cd ~/inference-master/loadgen/benchmark
```
Create `run_build.sh`.
```
#!/usr/bin/bash
#run_build.sh example

echo "Building loadgen..."
if [ ! -e loadgen_build ]; then mkdir loadgen_build; fi;
cd loadgen_build && cmake ../.. && make -j && cd ..
echo "Building test program..."
if [ ! -e build ]; then mkdir build; fi;
g++ --std=c++11 -O3 -I.. -o build/repro.exe repro.cpp -Lloadgen_build -lmlperf_loadgen -lpthread
```
```
chmod 775 run_build.sh
```
Run `./run_build.sh` and then move `build/repro.exe` into a parent directory.
```
mv build/repro.exe ./
```
Create run_test.sh.
```
#!/usr/bin/bash
#run_test.sh example

cd /home/user/inference-master/loadgen/benchmark
if [ ! -e build ]; then mkdir build; fi;
LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2 ./repro.exe 800000 0 4 2048
```
```
chmod 775 run_test.sh
```
Then go to `ptd_client_server` directory and start the client, assuming the director ip address is `192.168.1.2`.
The output would be located at `client-output-directory`.
The script `~/inference-master/loadgen/benchmark/build/run_test.sh` will be used as a workload being measured.
```
./client.py -a 192.168.1.2 -o client-output-directory \
    -w "/home/user/inference-master/loadgen/benchmark/run_test.sh" \
    -L "/home/user/inference-master/loadgen/benchmark/build" \
    -l "loadgen_example" -s -f -n fi.pool.ntp.org
```
### Result

After a successful run, you'll see these new files and directories on the server:
```
D:\ptd-logs
├── … (old entries skipped)
├── 2020-12-29_15-20-52_loadgen_example_ranging
│   ├── spl.txt                           ← power log
│   ├── mlperf_log_accuracy.json        ┐
│   ├── mlperf_log_detail.txt           │ ← loadgen log (if --send-logs is used)
│   ├── mlperf_log_summary.txt          │
│   └── mlperf_log_trace.json           ┘
└── 2020-12-29_15-20-52_loadgen_example_testing
    ├── spl.txt                           ← power log
    ├── mlperf_log_accuracy.json        ┐
    ├── mlperf_log_detail.txt           │ ← loadgen log (if --send-logs is used)
    ├── mlperf_log_summary.txt          │
    └── mlperf_log_trace.json           ┘
```
And these on the client:
```
client-output-directory
├── 2020-12-29_15-20-52_loadgen_example_ranging
│   ├── mlperf_log_accuracy.json
│   ├── mlperf_log_detail.txt
│   ├── mlperf_log_summary.txt
│   └── mlperf_log_trace.json
└── 2020-12-29_15-20-52_loadgen_example_testing
    ├── mlperf_log_accuracy.json
    ├── mlperf_log_detail.txt
    ├── mlperf_log_summary.txt
    └── mlperf_log_trace.json
```
spl.txt consists of the following lines:
```
Time,29-12-2020 15:20:11.575,Watts,41.960000,Volts,230.860000,Amps,0.321990,PF,0.564500,Mark,2021-02-02_00-01-37_loadgen_example_testing
Time,29-12-2020 15:20:12.571,Watts,39.700000,Volts,230.870000,Amps,0.306990,PF,0.560100,Mark,2021-02-02_00-01-37_loadgen_example_testing
Time,29-12-2020 15:20:13.574,Watts,44.010000,Volts,230.870000,Amps,0.334470,PF,0.570000,Mark,2021-02-02_00-01-37_loadgen_example_testing
```
## NTP Setup

To make sure the Loadgen logs and PTDaemon logs match, the system time should be synchronized on the client and the server.
Both the client and the server have an option to configure the NTP server address to sync with before running a workload.

### Linux

Prerequisites:
1. Install `ntpdate` binary. Ubuntu package: `ntpdate`.
2. Disable pre-existing `ntp` and `systemd-timesyncd` daemons if they are running.
   On Ubuntu: `systemctl disable systemd-timesyncd; systemctl stop systemd-timesyncd`,
              `systemctl disable ntp; systemctl stop ntp`.
3. Root priveleges are required. Either run the script as root, or set up a passwordless `sudo`.

The script will synchronize time using `ntpdate` binary.

### Windows
Prerequisites:
1. Run the script as an administrator.
2. Install `pywin32`: `python -m pip install pywin32`.

## Unexpected test termination

During the test, the client and the server maintain a persistent TCP connection.

In the case of unexpected client disconnection, the server terminates the power measurement and consider the test failed.
The client intentionally doesn't perform an attempt to reconnect to make the test strict.

Additionally, [TCP keepalive] is used to detect a stale connection and don't let the server wait indefinitely in case if the client is powered off during the test or the network cable is cut.
Keepalive packets are sent each 2 seconds, and we consider the connection broken after 10 missed keepalive responses.

[TCP keepalive]: https://en.wikipedia.org/wiki/Keepalive#TCP_keepalive
[inference]: https://github.com/mlcommons/inference