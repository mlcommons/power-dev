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
import logging
import os
import shutil
import socket
import subprocess
import time
import zipfile
from . import time_sync

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
    with zipfile.ZipFile(zip_filename, "x", zipfile.ZIP_DEFLATED) as zf:
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
            prog, max_help_position=35
        ),
    )

    optional = parser._action_groups.pop()
    required = parser.add_argument_group("required arguments")

    # fmt: off
    required.add_argument(
        "-a", "--addr", metavar="ADDR", type=str, required=True,
        help="server address")
    required.add_argument(
        "-w", "--run-workload", metavar="CMD", type=str, required=True,
        help="a shell command to run under power measurement")
    required.add_argument(
        "-L", "--loadgen-logs", metavar="INDIR", type=str, required=True,
        help="collect loadgen logs from INDIR")
    required.add_argument(
        "-o", "--output", metavar="OUTDIR", type=str, required=True,
        help="put logs into OUTDIR (copied from INDIR)")
    required.add_argument(
        "-n", "--ntp", metavar="ADDR", type=str, required=True,
        help="NTP server address")

    parser.add_argument(
        "-p", "--port", metavar="PORT", type=int, default=4950,
        help="server port, defaults to 4950")
    parser.add_argument(
        "-l", "--label", metavar="LABEL", type=str, default="",
        help="a label to include into the resulting directory name")
    parser.add_argument(
        "-s", "--send-logs", action="store_true",
        help="send loadgen logs to the server")
    parser.add_argument(
        "-f", "--force", action="store_true",
        help="force remove loadgen logs directory (INDIR)")
    parser.add_argument(
        "-S", "--stop-server", action="store_true",
        help="stop the server after processing this client")
    # fmt: on

    parser._action_groups.append(optional)
    args = parser.parse_args()

    if not common.check_label(args.label):
        parser.error(
            "invalid --label value: {args.label!r}. Should be alphanumeric or -_."
        )

    if args.port is None:
        args.port = common.DEFAULT_PORT
        logging.warning(f"Assuming default port (--port {common.DEFAULT_PORT}")

    if os.path.exists(args.loadgen_logs):
        if args.force:
            logging.warning(
                f"Removing old loadgen logs directory {args.loadgen_logs!r}"
            )
            shutil.rmtree(args.loadgen_logs)
        else:
            logging.fatal(
                f"The loadgen logs directory {args.loadgen_logs!r} already exists"
            )
            logging.fatal("Please remove it or specify --force argument")
            exit(1)

    common.mkdir_if_ne(args.output)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((args.addr, args.port))
    except OSError as e:
        s.close()
        logging.fatal(f"Could not connect to the server {args.addr}:{args.port} {e}")
        exit(1)

    serv = common.Proto(s)
    serv.enable_keepalive()

    # TODO: timeout and max msg size for recv
    magic = command(serv, common.MAGIC_CLIENT)
    if magic != common.MAGIC_SERVER:
        logging.error(
            f"Handshake failed, expected {common.MAGIC_SERVER!r}, got {magic!r}"
        )
        exit(1)
    del magic

    if args.stop_server:
        # Enable the "stop" flag on the server so it will stop after the client
        # disconnects.  We are sending this early to make sure the server
        # eventually will stop even if the client crashes unexpectedly.
        command(serv, "stop", check=True)

    def ntp_and_server_sync_check() -> None:
        if not time_sync.ntp_host_sync(args.ntp):
            logging.error("Could not synchronize time with NTP")
            exit()
        if not time_sync.remote_host_sync(
            lambda: float(command(serv, "time")), lambda: float(command(serv, "resync"))
        ):
            logging.error("Could not synchronize time with server")
            exit()

    ntp_and_server_sync_check()

    session = command(serv, f"new,{args.label}")
    if session is None or not session.startswith("OK "):
        logging.fatal("Could not start new session")
        exit(1)
    session = session[len("OK ") :]
    logging.info(f"Session id is {session!r}")

    for mode in ["ranging", "testing"]:
        logging.info(f"Running workload in {mode} mode")
        out = os.path.join(args.output, f"{session}_{mode}")

        # os.mkdir(out)

        ntp_and_server_sync_check()
        command(serv, f"session,{session},start,{mode}", check=True)

        logging.info(f"Running the workload {args.run_workload!r}")
        subprocess.run(args.run_workload, shell=True, check=True)

        command(serv, f"session,{session},stop,{mode}", check=True)

        if (
            not os.path.isdir(args.loadgen_logs)
            or len(os.listdir(args.loadgen_logs)) == 0
        ):
            logging.fatal(
                f"Expected {args.loadgen_logs!r} to be a directory containing loadgen logs, but it is not"
            )
            exit(1)

        shutil.move(args.loadgen_logs, out)

        if len(os.listdir(out)) == 0:
            logging.fatal(f"The directory {out!r} is empty")
            logging.fatal(
                "Please make sure that the provided workload command writes its "
                "output into the directory specified by environment variable $out"
            )
            exit(1)

        if args.send_logs:
            logging.info("Packing logs into zip and uploading to the server")
            create_zip(f"{out}.zip", out)
            logging.info(
                "Zip file size: " + common.human_bytes(os.stat(f"{out}.zip").st_size)
            )
            serv.send(f"session,{session},upload,{mode}")
            serv.send_file(f"{out}.zip")
            logging.info(serv.recv())
            os.remove(f"{out}.zip")

    logging.info("Done runs")

    command(serv, f"session,{session},done", check=True)

    logging.info("Successful exit")
