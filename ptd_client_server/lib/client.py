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
import inspect
import logging
import os
import socket
import subprocess
import time
import zipfile

from . import common


def command(server: common.Proto, command: str, check: bool = False) -> str:
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


def command_get_file(server: common.Proto, command: str, save_name: str) -> None:
    logging.info(f"Sending command to the server: {command!r}")
    log = server.command(command)
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


def main() -> None:
    common.init("client")

    parser = argparse.ArgumentParser(
        description="PTD client",
        formatter_class=lambda prog: argparse.RawDescriptionHelpFormatter(
            prog, max_help_position=30
        ),
        epilog=inspect.cleandoc(
            """
            The CMD could use the following environment variables:
              $ranging - "1" in the ranging mode, or "0" in the testing mode.
              $out     - Path to the output directory for this run.
                         It should be either "OUTDIR/ranging" or "OUTDIR/testing".
            """
        ),
    )

    # fmt: off
    parser.add_argument(
        "-a", "--addr", metavar="ADDR", type=str, required=True,
        help="server address")
    parser.add_argument(
        "-p", "--port", metavar="PORT", type=int, default=4950,
        help="server port, defaults to 4950")
    parser.add_argument(
        "-o", "--output", metavar="OUTDIR", type=str, required=True,
        help="output directory")
    parser.add_argument(
        "-n", "--ntp", metavar="ADDR", type=str,
        help="""NTP server address, optional""")
    parser.add_argument(
        "-l", "--label", metavar="LABEL", type=str, default="",
        help="""a label to inclide into the directory name at the server""")
    parser.add_argument(
        "-w", "--run-workload", metavar="CMD", type=str, required=True,
        help="""a shell command to run under power measurement""")
    # fmt: on

    args = parser.parse_args()

    if not common.check_label(args.label):
        parser.error(
            "invalid --label value: {args.label!r}. Should be alphanumeric or -_."
        )

    if args.port is None:
        args.port = common.DEFAULT_PORT
        logging.warning(f"Assuming default port (--port {common.DEFAULT_PORT}")

    if os.path.exists(args.output):
        logging.fatal(f"The output directory {args.output!r} already exists.")
        logging.fatal("Please remove it or select another directory.")
        exit(1)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((args.addr, args.port))
    serv = common.Proto(s)

    if command(serv, "hello") != "Hello from server!":
        logging.fatal("Not a server")
        exit(1)

    logging.info(f"Creating output directory {args.output!r}")
    os.mkdir(args.output)

    common.ntp_sync(args.ntp)

    session = command(serv, f"new,{args.label}")
    if session is None or not session.startswith("OK "):
        logging.fatal("Could not start new session")
        exit(1)
    session = session[len("OK ") :]
    logging.info(f"Session id is {session!r}")

    client_time1 = time.time()
    serv_time = float(command(serv, "time"))
    client_time2 = time.time()
    dt1 = 1000 * (client_time1 - serv_time)
    dt2 = 1000 * (client_time2 - serv_time)
    logging.info(f"The time difference is within range {dt1:.3}ms..{dt2:.3}ms")

    if max(abs(dt1), abs(dt2)) > 1000:
        logging.fatal(
            "The time difference between client and server is more than 1 second"
        )
        exit(1)

    for mode in ["ranging", "testing"]:
        logging.info(f"Running workload in {mode} mode")
        out = f"{args.output}/{mode}"

        os.mkdir(out)

        env = os.environ.copy()
        env["ranging"] = "1" if mode == "ranging" else "0"
        env["out"] = out

        common.ntp_sync(args.ntp)
        command(serv, f"session,{session},start,{mode}", check=True)

        logging.info("Running runWorkload")
        subprocess.run(args.run_workload, shell=True, check=True, env=env)

        command(serv, f"session,{session},stop,{mode}", check=True)

        logging.info("Packing logs into zip and uploading to the server")
        create_zip(f"{out}.zip", out)
        serv.send(f"session,{session},upload,{mode}")
        serv.send_file(f"{out}.zip")
        logging.info(serv.recv())
        os.remove(f"{out}.zip")

    logging.info("Done runs")

    command(serv, f"session,{session},done", check=True)

    logging.info("Successful exit")
