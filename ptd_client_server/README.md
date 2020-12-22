## Dependencies

* Python 3.7.
* PTDaemon (on the server)

## Description

This client-server application is intended to measure the power consumed during an execution of a list of workloads.

The server is intended to be run on the director (the machine on which PTDaemon runs), and the client is intended to be run on the SUT (system under test).

The client accepts a list of workloads and their settings and a command to be run for each setting.
The power is measured by the server during the command execution on a client.

The command is run twice for each setting: the first time in ranging mode, and the second time is in testing mode.

## Usage

Start a server (on a director):
```
./server.py -c server-config.conf
```

Then start a client (on a SUT), assuming the director is located at `192.168.100.200`.
The output would be located at `output-directory`.
The script `./run.sh` will be used as a workload being measured.
```
./client.py -a 192.168.100.200 -o output-directory --run-workload "./run.sh"
```

See `./client.py --help` for option description.

## Configuration examples

```sh
export MODEL_DIR=...
export DATA_DIR=...

./client.py \
	--ntp ntp.example.com \
	--label 'ssd-mobilenet-tf-offline' \
	--run-workload '
		cd /path/to/mlcommons/inference/vision/classification_and_detection &&
		./run_local.sh tf ssd-mobilenet cpu --scenario Offline --output "$out"/ssdmobilenet
	' \
	--output "$PWD/out" \
	-a 192.168.104.169
```

Server configuration:

```ini
[server]
# (Optional) NTP server to sync with before each measurement.
# See "NTP Setup" section in the README.md.
ntpServer: ntp.example.com

# A command to run PTDaemon.
ptdCommand: D:\PTD\ptd-windows-x86.exe -p 8888 -l D:\logs_ptdeamon.txt -e -y 49 C2PH13047V

# A port on that PTDaemon listens.
# Should be in sync with "ptdCommand".
ptdPort: 8888

# A path to a logfile that PTDaemon produces.
# Should be in sync with "ptdCommand".
ptdLogfile: D:\logs_ptdeamon.txt

# A directory to store output data.
# A new subdirectory will be created per each run.
outDir: D:\ptd-logs\
```


## NTP Setup

To make sure the Loadgen logs and PTDaemon logs match, the system time should be synchronized on the client and the server.
Both the client and the server have an option to configure the NTP server address to sync with before running a workload.

### Linux

Prerequisites:
1. Install `ntpdate` binary. Ubuntu package: `ntpdate`.
2. Disable pre-existing `ntp` daemon if it is running. On Ubuntu: `systemctl disable ntp; systemctl stop ntp`.
3. Root priveleges are required. Either run the script as root, or set up a passwordless `sudo`.

The script will synchronize time using `ntpdate` binary.

### Windows
Prerequisites:
1. Run the script as an administrator.

The script would enable and configure `w32time` service automatically.
