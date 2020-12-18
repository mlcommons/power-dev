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
import zipfile

import lib


def command(server: lib.Proto, command: str, check: bool = False) -> str:
    logging.info(f"Sending command to the server: {command!r}")
    response = server.command(command)
    if response is None:
        logging.fatal("The server is disconnected")
        exit(1)
    logging.info(f"Got response: {response!r}")
    if check and response != "OK":
        logging.fatal("Got an unexpecting response from the server")
        exit(1)
    return response


def command_get_file(server: lib.Proto, command: str, save_name: str) -> None:
    logging.info(f"Sending command to the server: {command!r}")
    log = serv.command(command)
    if log is None or not log.startswith("base64 "):
        logging.fatal("Could not get file from the server")
        exit(1)
    with open(save_name, "wb") as f:
        f.write(base64.b64decode(log[len("base64 ") :]))
    logging.info(f"Saving response to {save_name!r}")


def create_zip(zip_filename: str, dirname: str) -> None:
    with zipfile.ZipFile(zip_filename, "x") as zf:
        for folderName, subfolders, filenames in os.walk(dirname):
            for filename in filenames:
                filePath = os.path.join(folderName, filename)
                zipPath = os.path.relpath(filePath, dirname)
                zf.write(filePath, zipPath)


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
    "--ntp-server", metavar="ADDR", type=str,
    help="""NTP server address.""")
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
parser.add_argument(
    "--label", metavar="LABEL", type=str,
    help="""
        Optional label to include to the output sent to the server.
        If set, this label would be included in the directory name.
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

if args.ntp_server is None:
    args.ntp_server = config.get("ntpServer")

if args.label is not None:
    if not lib.check_label(args.label):
        logging.fatal("Error: invalid label {args.label!r}")
        exit(1)
    log_name_prefix = args.label + "-"
else:
    log_name_prefix = ""

if os.path.exists(args.output):
    logging.fatal(f"The output directory {args.output!r} already exists.")
    logging.fatal("Please remove it or select another directory.")
    exit(1)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((args.serverIpAddress, args.serverPort))
serv = lib.Proto(s)

if command(serv, "hello") != "Hello from server!":
    logging.fatal("Not a server")
    exit(1)

logging.info(f"Creating output directory {args.output!r}")
os.mkdir(args.output)

lib.ntp_sync(args.ntp_server)

command(serv, "init", check=True)

client_time1 = time.time()
serv_time = float(command(serv, "time"))
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

    if args.run_before is not None:
        logging.info("Running runBefore")
        subprocess.run(args.run_before, shell=True, check=True, env=env)

    lib.ntp_sync(args.ntp_server)
    command(serv, f"start-{mode},workload", check=True)

    logging.info("Running runWorkload")
    subprocess.run(args.run_workload, shell=True, check=True, env=env)

    command(serv, "stop", check=True)

    command_get_file(serv, "get-last-log", out + "/spl.txt")

    if args.run_after is not None:
        logging.info("Running runAfter")
        subprocess.run(args.run_after, shell=True, check=True, env=env)

    logging.info("Packing logs into zip and uploading to the server")
    create_zip(f"{out}.zip", out)
    serv.send(f"push-log,{log_name_prefix}{mode}")
    serv.send_file(f"{out}.zip")
    logging.info(serv.recv())


logging.info("Done runs")

command_get_file(serv, "get-log", args.output + "/spl-full.txt")

logging.info("Successful exit")
