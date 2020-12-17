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
import time

import lib

lib.init("client")

parser = argparse.ArgumentParser(description="PTD client")

# fmt: off
parser.add_argument(
    "-c", "--config", metavar="FILE", type=str,
    help="""
        Client configuration file path.
        Note that the same options could be configured through the command line.
    """)
parser.add_argument(
    "-p", "--serverPort", metavar="PORT", type=int, default=4950,
    help="Server port")
parser.add_argument(
    "-i", "--serverIpAddress", metavar="ADDR", type=str, required=True,
    help="Server IP address")
parser.add_argument(
    "-o", "--output", metavar="DIR", type=str, default="out",
    help="Output directory")
parser.add_argument(
    "--ntp-command", metavar="CMD", type=str,
    help="""A command to run after connecting to the server.""")
parser.add_argument(
    "--run-before", metavar="CMD", type=str,
    help="""
        A command to run before power measurement.
        Some preparation could be done here, if necessary.
    """)
parser.add_argument(
    "--run-workload", metavar="CMD", type=str,
    help="""
        A command to run under power measurement.
        An actual workload should be done here.
    """)
parser.add_argument(
    "--run-after", metavar="CMD", type=str,
    help="""
        A command to run after power measurement is done.
        A cleanup or some log processing could be done here, if necessary.
    """)
# fmt: on

args = parser.parse_args()
if args.config is not None:
    with open(args.config, "r") as f:
        config = json.load(f)
else:
    config = {}

if args.run_before is None:
    args.run_before = config.get("runBefore", "")

if args.run_workload is None:
    args.run_workload = config.get("runWorkload", None)
if args.run_workload is None:
    logging.fatal("--run-workload option is mandatory")
    exit(1)

if args.run_after is None:
    args.run_after = config.get("runAfter", "")

if args.ntp_command is None:
    args.ntp_command = config.get("ntpCommand", "")

if os.path.exists(args.output):
    logging.fatal(f"The output directory {args.output!r} already exists.")
    logging.fatal("Please remove it or select another directory.")
    exit(1)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((args.serverIpAddress, args.serverPort))
serv = lib.Proto(s)

if serv.command("hello") != "Hello from server!":
    logging.fatal("Not a server")
    exit(1)

logging.info(f"Creating output directory {args.output!r}")
os.mkdir(args.output)

logging.info(f"Running {args.ntp_command!r}")
subprocess.run(args.ntp_command, shell=True, check=True)

if serv.command("init") != "OK":
    exit(1)

client_time1 = time.time()
serv_time = float(serv.command("time"))
client_time2 = time.time()
dt1 = 1000 * (client_time1 - serv_time)
dt2 = 1000 * (client_time2 - serv_time)
logging.info(f"The time difference is in {dt1:.3}ms..{dt2:.3}ms")

for mode in ["ranging", "testing"]:
    logging.info(f"Running workload in {mode} mode")
    out = f"{args.output}/{mode}"

    os.mkdir(out)

    env = os.environ.copy()
    env["ranging"] = "1" if mode == "ranging" else "0"
    env["out"] = out

    logging.info("Running runBefore")
    subprocess.run(args.run_before, shell=True, check=True, env=env)

    if serv.command(f"start-{mode},workload") != "OK":
        exit(1)

    logging.info("Running runWorkload")
    subprocess.run(args.run_workload, shell=True, check=True, env=env)

    if serv.command("stop") != "OK":
        exit(1)

    log = serv.command("get-last-log")
    if log is None or not log.startswith("base64 "):
        exit(1)
    with open(out + "/spl.txt", "wb") as f:
        f.write(base64.b64decode(log[len("base64 ") :]))

    logging.info("Running runAfter")
    subprocess.run(args.run_after, shell=True, check=True, env=env)

logging.info("Done runs")

log = serv.command("get-log")
if log is None or not log.startswith("base64 "):
    exit(1)

with open(args.output + "/spl-full.txt", "wb") as f:
    f.write(base64.b64decode(log[len("base64 ") :]))

logging.info("Successful exit")
