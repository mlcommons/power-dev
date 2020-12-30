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
	--send-logs \
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

# (Optional) IP address and port to listen on
# Defaults to "0.0.0.0 4950" if not set
listen: 192.168.1.2 4950
```

## Logs

The purpose of this software is to produce two log files:
* A loadgen log which is generated on the SUT by running an inference benchmark.
* A power log that is generated on the server by PTDaemon.


The client has the following command-line options related to log files:

* `--output "$PWD/client-log-dir"`

  An output directory to store loadgen logs.
  It is expected that the workload command will place loadgen logs into the location specified by the `"$out"` environment variable, which is pointed either to `ranging` or `testing` subdirectory inside the output directory.
  The client does not override an existing directory.

* `--send-logs`

  If enabled, then the loadgen log will be sent to the server and stored alongside the power log.

* `--label "mylabel"`

  A human-readable label.
  The label is used later at the server to distinguish between log directories.


The server has the following configuration keys related to log files:

* `ptdLogfile: D:\logs_ptdeamon.txt` — a path to the full PTDaemon log.

  Note that in the current implementation this file is considered temporary and may be overwritten. 

* `outDir: D:\ptd-logs\` — a directory to store output logs.

  After each run, a new sub-directory inside this directory created, containing both a loadgen log and a power log for this run.
  The name of this sub-directory consists of date, time, label, and mode (ranging/testing).
  * The loadgen log is fetched from the client, if the `--send-logs` option is enabled.
    The name of the directory is determined by the workload script running on the SUT, e.g. `ssdmobilenet`.
  * The power log, named `spl.txt`, is extracted from the full PTDaemon log (`ptdLogfile`).

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

# Keep-alive

TODO: describe keep-alive

# Result

After a successful run, you'll see these new files and directories on the server:
```
D:\ptd-logs\
├── … (old entries skipped)
├── 2020-12-28_15-20-52_mylabel_ranging
│   ├── spl.txt                               ← power log
│   └── ssdmobilenet                          ← loadgen log (if --send-logs is used)
│       ├── mlperf_log_accuracy.json
│       ├── mlperf_log_detail.txt
│       ├── mlperf_log_summary.txt
│       └── mlperf_log_trace.json
└── 2020-12-28_15-20-52_mylabel_testing
    ├── spl.txt                               ← power log
    └── ssdmobilenet                          ← loadgen log (if --send-logs is used)
        ├── mlperf_log_accuracy.json
        ├── mlperf_log_detail.txt
        ├── mlperf_log_summary.txt
        └── mlperf_log_trace.json
```

And these on the client:
```
$PWD/client-log-dir
├── ranging
│   └── ssdmobilenet                          ← loadgen log
│       ├── mlperf_log_accuracy.json
│       ├── mlperf_log_detail.txt
│       ├── mlperf_log_summary.txt
│       └── mlperf_log_trace.json
└── testing
    └── ssdmobilenet                          ← loadgen log
        ├── mlperf_log_accuracy.json
        ├── mlperf_log_detail.txt
        ├── mlperf_log_summary.txt
        └── mlperf_log_trace.json
```
