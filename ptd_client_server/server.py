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

from __future__ import annotations
from typing import Optional, Dict, Tuple
from decimal import Decimal
import argparse
import base64
import configparser
import datetime
import logging
import os
import re
import socket
import subprocess
import sys
import time
import zipfile

import lib


RE_PTD_LOG = re.compile(
    r"""^
        Time,  [^,]*,
        Watts, [^,]*,
        Volts, (?P<v> [^,]* ),
        Amps,  (?P<a> [^,]* ),
        .*,
        Mark,  (?P<mark> [^,]* )
    $""",
    re.X,
)


def max_volts_amps(log_fname: str, mark: str) -> Tuple[str, str]:
    maxVolts = Decimal("-1")
    maxAmps = Decimal("-1")
    with open(log_fname, "r") as f:
        for line in f:
            m = RE_PTD_LOG.match(line.rstrip("\r\n"))
            if m and m["mark"] == mark:
                maxVolts = max(maxVolts, Decimal(m["v"]))
                maxAmps = max(maxAmps, Decimal(m["a"]))
    if maxVolts <= 0 or maxAmps <= 0:
        raise RuntimeError(f"Could not find values for {mark!r}")
    return str(maxVolts), str(maxAmps)


def read_log(log_fname: str, mark: str) -> str:
    result = []
    with open(log_fname, "r") as f:
        for line in f:
            m = RE_PTD_LOG.match(line.rstrip("\r\n"))
            if m and m["mark"] == mark:
                result.append(line)
    return "".join(result)


class ServerConfig:
    def __init__(self, filename: str) -> None:
        conf = configparser.ConfigParser()
        conf.read_file(open(filename))

        try:
            serv_conf = conf["server"]
        except KeyError:
            logging.fatal(
                "Server section is empty in the configuration file. "
                "Please add server section."
            )
            exit(1)

        all_options = {
            "ntpServer",
            "outDir",
            "ptdCommand",
            "ptdLogfile",
            "ptdPort",
        }

        self.ntp_server = serv_conf.get("ntpServer")

        try:
            ptd_port = serv_conf["ptdPort"]
            self.ptd_logfile = serv_conf["ptdLogfile"]
            self.out_dir = serv_conf["outDir"]
            self.ptd_command = serv_conf["ptdCommand"]
        except KeyError as e:
            logging.fatal(f"{filename}: missing option: {e.args[0]!r}")
            exit(1)

        try:
            self.ptd_port = int(ptd_port)
        except ValueError:
            logging.fatal(f"{filename}: could not parse {ptd_port!r} as int")
            exit(1)

        unused_options = set(serv_conf.keys()) - set((i.lower() for i in all_options))
        if len(unused_options) != 0:
            logging.warning(
                f"{filename}: ignoring unknown options: {', '.join(unused_options)}"
            )

        unused_sections = set(conf.sections()) - {"server"}
        if len(unused_sections) != 0:
            logging.warning(
                f"{filename}: ignoring unknown sections: {', '.join(unused_sections)}"
            )


class Ptd:
    def __init__(self, command: str, port: int) -> None:
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._socket: Optional[socket.socket] = None
        self._proto: Optional[lib.Proto] = None
        self._command = command
        self._port = port

    def start(self) -> bool:
        if self._process is not None:
            return False
        if sys.platform == "win32":
            # shell=False:
            #   On Windows, we don't need a shell to run a command from a single
            #   string.  On the other hand, calling self._process.terminate()
            #   will terminate the shell (cmd.exe), but not the an actual
            #   command.  Thus, shell=False.
            #
            # creationflags=subprocess.CREATE_NEW_PROCESS_GROUP:
            #   We do not want to pass ^C from the current console to the
            #   PTDaemon.  Instead, we terminate it explicitly in self.stop().
            self._process = subprocess.Popen(
                self._command,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            self._process = subprocess.Popen(self._command, shell=True)

        retries = 100
        s = None
        while s is None and retries > 0:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.connect(("127.0.0.1", self._port))
            except ConnectionRefusedError:
                if lib.sig.stopped:
                    exit()
                time.sleep(0.1)
                s = None
                retries -= 1
        if s is None:
            logging.error("Could not connect to PTD")
            self.stop()
            return False
        self._socket = s
        self._proto = lib.Proto(s)

        if self.cmd("Hello") != "Hello, PTDaemon here!":
            logging.error("This is not PTDaemon")
            return False

        self.cmd("Identify")  # reply traced in logs

        logging.info("Connected to PTDaemon")
        return True

    def stop(self) -> None:
        if self._proto is not None:
            self.cmd("Stop")
            self._proto = None

        if self._socket is not None:
            self._socket.close()
            self._socket = None

        if self._process is not None:
            logging.info("Stopping ptd...")
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process = None

    def running(self) -> bool:
        return self._process is not None

    def cmd(self, cmd: str) -> Optional[str]:
        if self._proto is None:
            return None
        logging.info(f"Sending to ptd: {cmd!r}")
        self._proto.send(cmd)
        reply = self._proto.recv()
        logging.info(f"Reply from ptd: {reply!r}")
        return reply


class Server:
    def __init__(self, config: ServerConfig) -> None:
        self._ptd = Ptd(config.ptd_command, config.ptd_port)
        self._mode: Optional[str] = None
        self._mark: Optional[str] = None
        self._ranging_table: Dict[str, Tuple[str, str]] = {}
        self._config = config

    def close(self) -> None:
        self._ptd.stop()

    def handle_connection(self, p: lib.Proto) -> None:
        self._ranging_table = {}
        self._mode = None
        self._mark = None

        if os.path.exists(self._config.ptd_logfile):
            os.remove(self._config.ptd_logfile)

        try:
            while True:
                with lib.sig:
                    cmd = p.recv()

                if cmd is None:
                    logging.info("Connection closed")
                    break
                logging.info(f"Got command from the client {cmd!r}")

                try:
                    reply = self._handle_cmd(cmd, p)
                except KeyboardInterrupt:
                    break
                except Exception:
                    logging.exception("Got an exception")
                    reply = "Error: exception"

                if len(reply) < 1000:
                    logging.info(f"Sending reply to client {reply!r}")
                else:
                    logging.info(
                        f"Sending reply to client {reply[:50]!r}... len={len(reply)}"
                    )
                p.send(reply)
        finally:
            self._ptd.stop()

    def _handle_cmd(self, cmd: str, p: lib.Proto) -> str:
        cmd = cmd.split(",")
        if len(cmd) == 0:
            return "..."
        if cmd[0] == "hello":
            return "Hello from server!"
        if cmd[0] == "time":
            return str(time.time())
        if cmd[0] == "init":
            lib.ntp_sync(config.ntp_server)
            if not self._ptd.start():
                return "Error"
            return "OK"
        if cmd[0] == "start-ranging" and len(cmd) == 2:
            self._ptd.cmd("SR,V,300")
            self._ptd.cmd("SR,A,Auto")
            with lib.sig:
                time.sleep(10)
            logging.info("Starting ranging mode")
            self._ptd.cmd(f"Go,1000,0,ranging-{cmd[1]}")
            self._mode = "ranging"
            self._mark = cmd[1]
            return "OK"
        if cmd[0] == "start-testing" and len(cmd) == 2:
            maxVolts, maxAmps = self._ranging_table[cmd[1]]
            self._ptd.cmd(f"SR,V,{maxVolts}")
            self._ptd.cmd(f"SR,A,{maxAmps}")
            with lib.sig:
                time.sleep(10)
            logging.info("Starting testing mode")
            self._ptd.cmd(f"Go,1000,0,testing-{cmd[1]}")
            self._mode = "testing"
            self._mark = cmd[1]
            return "OK"
        if cmd[0] == "stop":
            if self._mark is None:
                return "Error"
            self._ptd.cmd("Stop")
            if self._mode == "ranging":
                item = max_volts_amps(self._config.ptd_logfile, "ranging-" + self._mark)
                logging.info(f"Result for {self._mark}: {item}")
                self._ranging_table[self._mark] = item
            self._last_log = read_log(
                self._config.ptd_logfile, f"{self._mode}-{self._mark}"
            )
            self._mode = None
            self._mark = None
            return "OK"
        if cmd[0] == "get-last-log":
            return "base64 " + base64.b64encode(self._last_log.encode()).decode()
        if cmd[0] == "get-log":
            with open(self._config.ptd_logfile, "rb") as f:
                data = f.read()
            return "base64 " + base64.b64encode(data).decode()
        if cmd[0] == "push-log" and len(cmd) == 2:
            label = cmd[1]
            if not lib.check_label(label):
                return "Error: invalid label"
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            dirname = os.path.join(self._config.out_dir, timestamp + "_" + label)
            try:
                p.recv_file(dirname + ".zip")
                with zipfile.ZipFile(dirname + ".zip", "r") as zf:
                    zf.extractall(dirname)
            finally:
                try:
                    os.remove(dirname + ".zip")
                except OSError:
                    pass
            return "OK"

        return "Error: unknown command"


lib.init("ptd-server")

parser = argparse.ArgumentParser(description="Server for communication with PTD")

# fmt: off
parser.add_argument("-p", "--serverPort", metavar="PORT", type=int, help="Server port", default=4950)
parser.add_argument("-i", "--ipAddress", metavar="IP", type=str, default="0.0.0.0")
parser.add_argument("-c", "--configurationFile", metavar="FILE", type=str, help="", default="server.conf")
# fmt: on
args = parser.parse_args()

config = ServerConfig(args.configurationFile)

if not os.path.exists(config.out_dir):
    try:
        os.mkdir(config.out_dir)
    except FileNotFoundError:
        logging.fatal(
            f"Could not create directory {config.out_dir!r}. "
            "Make sure all intermediate directories exit."
        )
        exit(1)

lib.ntp_sync(config.ntp_server)

server = Server(config)
try:
    lib.run_server(args.ipAddress, args.serverPort, server.handle_connection)
except KeyboardInterrupt:
    pass
finally:
    server.close()
