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
import zipfile

from typing import Callable
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


def check_paths(loadgen_logs: str, output: str, force: bool) -> None:
    loadgen_logs_dir = os.path.abspath(loadgen_logs)
    output_dir = os.path.abspath(output)

    if loadgen_logs_dir == output_dir:
        logging.fatal(
            f"INDIR ({loadgen_logs!r}) and OUTDIR ({output!r}) should not be the same directory"
        )
        exit(1)

    if loadgen_logs_dir == os.path.commonpath([loadgen_logs_dir, output_dir]):
        logging.fatal(
            f"OUTDIR ({output!r}) should not be the INDIR subdirectory ({loadgen_logs!r})"
        )
        exit(1)

    if os.path.exists(loadgen_logs):
        if force:
            logging.warning(f"Removing old loadgen logs directory {loadgen_logs!r}")
            shutil.rmtree(loadgen_logs)
        else:
            logging.fatal(f"The loadgen logs directory {loadgen_logs!r} already exists")
            logging.fatal("Please remove it or specify --force argument")
            exit(1)


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


def create_zip_logs(zip_filename: str, dirname: str) -> None:
    with zipfile.ZipFile(zip_filename, "x", zipfile.ZIP_DEFLATED) as zf:
        client_logs_path = os.path.join(dirname, "client_logs.txt")
        zf.write(client_logs_path, os.path.relpath(client_logs_path, dirname))


def main() -> None:
    common.init("client")

    common.system_check()

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
    common.log_redirect.start()

    parser._action_groups.append(optional)
    args = parser.parse_args()

    if not common.check_label(args.label):
        parser.error(
            "invalid --label value: {args.label!r}. Should be alphanumeric or -_."
        )

    if args.port is None:
        args.port = common.DEFAULT_PORT
        logging.warning(f"Assuming default port (--port {common.DEFAULT_PORT}")

    check_paths(args.loadgen_logs, args.output, args.force)

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

    def sync_check() -> None:
        if not time_sync.sync(
            args.ntp,
            lambda: float(command(serv, "time")),
            lambda: command(serv, "set_ntp"),
        ):
            exit()

    sync_check()

    session = command(serv, f"new,{args.label}")
    if session is None or not session.startswith("OK "):
        logging.fatal("Could not start new session")
        exit(1)
    session = session[len("OK ") :]
    logging.info(f"Session id is {session!r}")

    common.log_sources()
    out_dir = os.path.join(args.output, session)
    os.mkdir(out_dir)

    def send_logs(directory: str, mode: str, create_zip: Callable[[], None]) -> None:
        if not args.send_logs:
            return
        logging.info("Packing logs into zip and uploading to the server")
        create_zip()
        logging.info(
            "Zip file size: " + common.human_bytes(os.stat(f"{directory}.zip").st_size)
        )
        serv.send(f"session,{session},upload,{mode}")
        serv.send_file(f"{directory}.zip")
        logging.info(serv.recv())
        os.remove(f"{directory}.zip")

    for mode in ["ranging", "testing"]:
        logging.info(f"Running workload in {mode} mode")
        out = os.path.join(out_dir, mode)

        sync_check()
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

        send_logs(out, mode, lambda: create_zip(f"{out}.zip", out))

    logging.info("Done runs")

    common.log_redirect.stop(os.path.join(out_dir, "client_logs.txt"))

    send_logs(
        out_dir, "receiving_logs", lambda: create_zip_logs(f"{out_dir}.zip", out_dir)
    )

    command(serv, f"session,{session},done", check=True)

    logging.info("Successful exit")
