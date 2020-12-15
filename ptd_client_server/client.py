#!/usr/bin/env python3
# Copyright 2018 The MLPerf Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# =============================================================================

import argparse
import base64
import json
import logging
import os
import socket
import subprocess
import sys
import time

import lib

lib.init("client")

parser = argparse.ArgumentParser(description="PTD client")

# fmt: off
parser.add_argument("-p", "--serverPort", metavar="PORT", type=int, help="Server port", default=4950)
parser.add_argument("-i", "--serverIpAddress", metavar="ADDR", type=str, help="Server IP address", required=True)
parser.add_argument("-c", "--config", metavar="FILE", type=str, help="Client configuration file path", default="./client.conf")
parser.add_argument("-o", "--output", metavar="DIR", type=str, help="Output directory", default="out")
# fmt: on

args = parser.parse_args()
with open(args.config, "r") as f:
    config = json.load(f)

if os.path.exists(args.output):
    logging.fatal(f"The output directory {args.output!r} already exists.")
    logging.fatal(f"Please remove it or select another directory.")
    exit(1)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((args.serverIpAddress, args.serverPort))
serv = lib.Proto(s)

if serv.command("hello") != "Hello from server!":
    logging.fatal("Not a server")
    exit(1)

logging.info(f"Creating output directory {args.output!r}")
os.mkdir(args.output)

logging.info(f"Running {config['ntpCommand']!r}")
subprocess.run(config["ntpCommand"], shell=True, check=True)

if serv.command("init") != "OK":
    exit(1)

client_time1 = time.time()
serv_time = float(serv.command("time"))
client_time2 = time.time()
dt1 = 1000 * (client_time1 - serv_time)
dt2 = 1000 * (client_time2 - serv_time)
logging.info(f"The time difference is in {dt1:.3}ms..{dt2:.3}ms")

for mode in ["ranging", "testing"]:
    for workload in config["workloads"]:
        logging.info(f"Running workload {workload['name']!r} in mode {mode!r}")

        for n, setting in enumerate(workload["settings"]):
            out = f"{args.output}/{workload['name']}-{n}-{mode}/"

            os.mkdir(out)

            env = os.environ.copy()
            env["workload"] = workload["name"]
            env["run"] = str(n)
            env["setting"] = setting
            env["ranging"] = "1" if mode == "ranging" else "0"
            env["out"] = out

            logging.info(f"Running runBefore")
            subprocess.run(config["runBefore"], shell=True, check=True, env=env)

            if serv.command(f"start-{mode},{workload['name']}-{n}") != "OK":
                exit(1)

            logging.info(f"Running runWorkload")
            subprocess.run(config["runWorkload"], shell=True, check=True, env=env)

            if serv.command(f"stop") != "OK":
                exit(1)

            log = serv.command(f"get-last-log")
            if log is None or not log.startswith("base64 "):
                exit(1)
            with open(out + "/spl.txt", "wb") as f:
                f.write(base64.b64decode(log[len("base64 ") :]))

            logging.info(f"Running runAfter")
            subprocess.run(config["runAfter"], shell=True, check=True, env=env)

logging.info("Done runs")

log = serv.command(f"get-log")
if log is None or not log.startswith("base64 "):
    exit(1)

with open(args.output + "/spl-full.txt", "wb") as f:
    f.write(base64.b64decode(log[len("base64 ") :]))

logging.info("Successful exit")
