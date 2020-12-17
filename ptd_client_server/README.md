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
./server.py -c server-config.json
```

Start a client (on a SUT), assuming the director is located at `192.168.100.200`.
The output would be located at `output-directory`.
```
./client.py -c client-config.json -i 192.168.100.200 -o output-directory
```

## Configuration examples

If you'll use these examples, make sure you'll remove all comments starting with `//`.

Client configuration:

```javascript
{
  // An command to run after connecting to the server.
  "ntpCommand": "sudo /usr/sbin/ntpdate time.windows.com || true",

  // The following are three shell commands to be executed for each workload and setting.
  // Each command have the following environment variables:
  //   "$workload" - workload name (which is specified in this file)
  //   "$setting"  - a setting for the current workload (which is specified in this file)
  //   "$out"      - path to the output directory for this run

  // A command to run before power measurement.
  // Some preparation could be done here, if necessary.
  "runBefore": "",

  // A command to run under power measurement.
  // An actual workload should be done here.
  "runWorkload":
    "cd ~/loadgen/benchmark; build/repro.exe $setting",

  // A command to run after power measurement is done.
  // A cleanup or some log processing could be done here, if necessary.
  // Here is an example of a command that copies loadgen logs to the output directory.
  "runAfter":
    "mkdir -p -- \"$out\"/loadgen/gnmt; cp -a -- ~/loadgen/benchmark/build/mlperf* \"$out\"/loadgen/gnmt",


  // A list of workloads.
  // Each workload has a name and a list of settings.
  "workloads": [
     { "name": "W1",
       "settings": [ "S1", "S2" ]
     },
     { "name": "W2",
       "settings": [ "S3", "S4", "S5" ]
     }
  ]
}
```


Server configuration:

```
[server]
# An command to run when a client connects.
# Here is an example of a command for Windows that enables NTP service and triggers a resync.
ntpCommand: w32tm /resync || ( net start w32time && w32tm /resync )

# A command to run PTDaemon.
ptdCommand: D:\work\spec_ptd-main\PTD\ptd-windows-x86.exe -p 8888 -l D:\logs_ptdeamon.txt -e -y 49 C2PH13047V

# A port on that PTDaemon listens.
# Should be in sync with "ptdCommand".
ptdPort: 8888

# A path to a logfile that PTDaemon produces.
# Should be in sync with "ptdCommand".
ptdLogfile: D:\logs_ptdeamon.txt
```
