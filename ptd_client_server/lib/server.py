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
from decimal import Decimal
from enum import Enum
from ipaddress import ip_address
from typing import Optional, Dict, Tuple
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

from . import common


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

ANALYZER_SLEEP_SECONDS: float = 10

if os.getenv("MLPP_DEBUG") is not None:
    ANALYZER_SLEEP_SECONDS = 0.5


class MeasurementEndedTooFastError(Exception):
    pass


class MaxVoltsAmpsNegativeValuesError(Exception):
    pass


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
        raise MaxVoltsAmpsNegativeValuesError(f"Could not find values for {mark!r}")
    return str(maxVolts), str(maxAmps)


def read_log(log_fname: str, mark: str) -> str:
    # TODO: The log file grows over time and never cleared.
    #       Probably, we need to fseek() here instead of reading from the start.
    result = []
    with open(log_fname, "r") as f:
        for line in f:
            m = RE_PTD_LOG.match(line.rstrip("\r\n"))
            if m and m["mark"] == mark:
                result.append(line)
    return "".join(result)


def exit_with_error_msg(error_msg: str) -> None:
    logging.fatal(error_msg)
    exit(1)


def get_host_port_from_listen_string(listen_str: str) -> Tuple[str, int]:
    try:
        host, port = listen_str.split(" ")
    except ValueError:
        raise ValueError(f"could not parse listen option {listen_str}")
    try:
        ip_address(host)
    except ValueError:
        raise ValueError(f"wrong listen option ip address {ip_address}")
    try:
        int_port = int(port)
    except ValueError:
        raise ValueError(f"could not parse listen option port {port} as integer")
    return (host, int_port)


class ServerConfig:
    def __init__(self, filename: str) -> None:
        conf = configparser.ConfigParser()
        try:
            conf.read_file(open(filename))
        except FileNotFoundError:
            exit_with_error_msg(f"Configuration file '{filename}' does not exist.")

        try:
            serv_conf = conf["server"]
        except KeyError:
            exit_with_error_msg(
                "Server section is empty in the configuration file. "
                "Please add server section."
            )

        all_options = {
            "ntpServer",
            "outDir",
            "ptdCommand",
            "ptdLogfile",
            "ptdPort",
            "listen",
        }

        self.ntp_server = serv_conf.get("ntpServer")

        try:
            ptd_port = serv_conf["ptdPort"]
            self.ptd_logfile = serv_conf["ptdLogfile"]
            self.out_dir = serv_conf["outDir"]
            self.ptd_command = serv_conf["ptdCommand"]
        except KeyError as e:
            exit_with_error_msg(f"{filename}: missing option: {e.args[0]!r}")

        try:
            listen_str = serv_conf["listen"]
            try:
                self.host, self.port = get_host_port_from_listen_string(listen_str)
            except ValueError as e:
                exit_with_error_msg(f"{filename}: {e.args[0]}")
        except KeyError:
            self.host, self.port = (common.DEFAULT_IP_ADDR, common.DEFAULT_PORT)
            logging.warning(
                f"{filename}: There is no listen option. Server use {self.host}:{self.port}"
            )

        try:
            self.ptd_port = int(ptd_port)
        except ValueError:
            exit_with_error_msg(f"{filename}: could not parse {ptd_port!r} as int")

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
        self._proto: Optional[common.Proto] = None
        self._command = command
        self._port = port
        self._init_Amps: Optional[str] = None
        self._init_Volts: Optional[str] = None

    def start(self) -> None:
        try:
            self._start()
        except Exception:
            logging.exception("Could not start PTDaemon")
            exit(1)

    def _start(self) -> None:
        if self._process is not None:
            return
        if sys.platform == "win32":
            # shell=False:
            #   On Windows, we don't need a shell to run a command from a single
            #   string.  On the other hand, calling self._process.terminate()
            #   will terminate the shell (cmd.exe), but not the an actual
            #   command.  Thus, shell=False.
            #
            # creationflags=subprocess.CREATE_NEW_PROCESS_GROUP:
            #   We do not want to pass ^C from the current console to the
            #   PTDaemon.  Instead, we terminate it explicitly in self.terminate().
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
            if self._process.poll() is not None:
                raise RuntimeError("PTDaemon unexpectedly terminated")
            try:
                s.connect(("127.0.0.1", self._port))
            except ConnectionRefusedError:
                if common.sig.stopped:
                    exit()
                time.sleep(0.1)
                s = None
                retries -= 1
        if s is None:
            self.terminate()
            raise RuntimeError("Could not connect to PTDaemon")
        self._socket = s
        self._proto = common.Proto(s)

        if self.cmd("Hello") != "Hello, PTDaemon here!":
            raise RuntimeError("This is not PTDaemon")

        self.cmd("Identify")  # reply traced in logs

        logging.info("Connected to PTDaemon")

        self._get_initial_range()

    def stop(self) -> None:
        self.cmd("Stop")

    def terminate(self) -> None:
        if self._proto is not None:
            self.cmd("Stop")
            self.cmd(f"SR,V,{self._init_Volts}")
            self.cmd(f"SR,A,{self._init_Amps}")
            logging.info(
                f"Set initial values for Amps {self._init_Amps} and Volts {self._init_Volts}"
            )
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
        if reply is None:
            exit_with_error_msg("Got no reply from PTDaemon")
        logging.info(f"Reply from ptd: {reply!r}")
        return reply

    def _get_initial_range(self) -> None:
        # Normal Response: ?Ranges,{Amp Autorange},{Amp Range},{Volt Autorange},{Volt Range}\r\n?
        # Values: for autorange settings, -1 indicates ?unknown?, 0 = disabled, 1 = enabled
        # For range values, -1.0 indicates ?unknown?, >0 indicates actual value
        response = self.cmd("RR")
        if response is None or response == "":
            logging.error("Can not get initial range")
            exit(1)

        response_list = response.split(",")

        def get_range_from_ranges_list(param_num: int, setting_name: str) -> str:
            try:
                if (
                    response_list[param_num] == "0"
                    and float(response_list[param_num + 1]) > 0
                ):
                    return response_list[param_num + 1]
            except (ValueError, IndexError):
                logging.warning(f"Can not get ptd range value for {setting_name}")
                return "Auto"
            return "Auto"

        self._init_Amps = get_range_from_ranges_list(1, "Amps")
        self._init_Volts = get_range_from_ranges_list(3, "Volts")
        logging.info(
            f"Initial range for Amps is {self._init_Amps} for Volts is {self._init_Volts}"
        )


class Server:
    def __init__(self, config: ServerConfig) -> None:
        self.session: Optional[Session] = None
        self._config = config
        self._ptd = Ptd(config.ptd_command, config.ptd_port)

    def handle_connection(self, p: common.Proto) -> None:
        p.enable_keepalive()
        try:
            while True:
                with common.sig:
                    cmd = p.recv()
                if cmd is None:
                    logging.info("Connection closed")
                    break
                logging.info(f"Got command from the client {cmd!r}")

                try:
                    reply = self._handle_cmd(cmd, p)
                except KeyboardInterrupt:
                    break
                except MeasurementEndedTooFastError as e:
                    logging.error(f"Got an exception: {e.args[0]}")
                    reply = f"Error: {e.args[0]}"
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
            if self.session is not None:
                logging.warning("Client connection closed unexpectedly")
                self._drop_session()

    def _handle_cmd(self, cmd: str, p: common.Proto) -> str:
        cmd = cmd.split(",")
        if len(cmd) == 0:
            return "..."
        if cmd[0] == "hello":
            return "Hello from server!"
        if cmd[0] == "time":
            return str(time.time())
        if cmd[0] == "new" and len(cmd) == 2:
            if self.session is not None:
                self.session.drop()
            if not common.check_label(cmd[1]):
                return "Error: invalid label"
            self.session = Session(self, cmd[1])
            return "OK " + self.session._id
        if cmd[0] == "session" and len(cmd) >= 3:
            if self.session is None or (self.session._id != cmd[1] and "*" != cmd[1]):
                return "Error: unknown session"
            cmd = cmd[2:]

            unbool = ["Error", "OK"]

            if cmd == ["start", "ranging"]:
                return unbool[self.session.start(Mode.RANGING)]
            elif cmd == ["start", "testing"]:
                return unbool[self.session.start(Mode.TESTING)]

            if cmd == ["stop", "ranging"]:
                return unbool[self.session.stop(Mode.RANGING)]
            if cmd == ["stop", "testing"]:
                return unbool[self.session.stop(Mode.TESTING)]

            if cmd == ["upload", "ranging"] or cmd == ["upload", "testing"]:
                mode = Mode.RANGING if cmd[1] == "ranging" else Mode.TESTING
                fname = os.path.join(
                    self._config.out_dir, self.session._id + cmd[1] + ".tmp"
                )
                result = False
                try:
                    p.recv_file(fname)
                    result = self.session.upload(mode, fname)
                finally:
                    try:
                        os.remove(fname)
                    except OSError:
                        pass
                return unbool[result]

            if cmd == ["done"]:
                self._drop_session()
                return "OK"

            return "Error Unknown session command"

        return "Error"

    def _drop_session(self) -> None:
        if self.session is not None:
            try:
                self.session.drop()
            finally:
                self.session = None

    def close(self) -> None:
        try:
            self._drop_session()
        finally:
            self._ptd.terminate()


class SessionState(Enum):
    INITIAL = 0
    RANGING = 1
    RANGING_DONE = 2
    TESTING = 3
    TESTING_DONE = 4
    DONE = 5


class Mode(Enum):
    RANGING = 0
    TESTING = 1


class Session:
    def __init__(self, server: Server, label: str) -> None:
        self._server: Server = server
        self._go_command_time: Optional[float] = None
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._id: str = timestamp + "_" + label if label != "" else timestamp

        # State
        self._state = SessionState.INITIAL
        self._maxAmps: Optional[str] = None
        self._maxVolts: Optional[str] = None

    def start(self, mode: Mode) -> bool:
        if mode == Mode.RANGING and self._state == SessionState.RANGING:
            return True
        if mode == Mode.TESTING and self._state == SessionState.TESTING:
            return True

        if mode == Mode.RANGING and self._state == SessionState.INITIAL:
            self._server._ptd.start()

            common.ntp_sync(self._server._config.ntp_server)

            self._server._ptd.cmd("SR,V,Auto")
            self._server._ptd.cmd("SR,A,Auto")
            with common.sig:
                time.sleep(ANALYZER_SLEEP_SECONDS)
            logging.info("Starting ranging mode")
            self._server._ptd.cmd(f"Go,1000,0,{self._id}_ranging")
            self._go_command_time = time.monotonic()

            self._state = SessionState.RANGING

            return True

        if mode == Mode.TESTING and self._state == SessionState.RANGING_DONE:
            self._server._ptd.start()

            common.ntp_sync(self._server._config.ntp_server)

            self._server._ptd.cmd(f"SR,V,{self._maxVolts}")
            self._server._ptd.cmd(f"SR,A,{self._maxAmps}")
            with common.sig:
                time.sleep(ANALYZER_SLEEP_SECONDS)
            logging.info("Starting testing mode")
            self._server._ptd.cmd(f"Go,1000,0,{self._id}_testing")

            self._state = SessionState.TESTING

            return True

        # Unexpected state
        return False

    def stop(self, mode: Mode) -> bool:
        if mode == Mode.RANGING and self._state == SessionState.RANGING_DONE:
            return True
        if mode == Mode.TESTING and self._state == SessionState.TESTING_DONE:
            return True

        # TODO: handle exceptions?

        if mode == Mode.RANGING and self._state == SessionState.RANGING:
            self._state = SessionState.RANGING_DONE
            self._server._ptd.stop()
            assert self._go_command_time is not None
            test_duration = time.monotonic() - self._go_command_time
            dirname = os.path.join(self._server._config.out_dir, self._id + "_ranging")
            os.mkdir(dirname)
            with open(os.path.join(dirname, "spl.txt"), "w") as f:
                f.write(
                    read_log(self._server._config.ptd_logfile, self._id + "_ranging")
                )
            try:
                self._maxVolts, self._maxAmps = max_volts_amps(
                    self._server._config.ptd_logfile, self._id + "_ranging"
                )
            except MaxVoltsAmpsNegativeValuesError as e:
                if test_duration < 1:
                    raise MeasurementEndedTooFastError(
                        f"the ranging measurement ended too fast (less than 1 second), no PTDaemon logs generated for {self._id!r}"
                    ) from e
                else:
                    raise
            self._go_command_time = None
            return True

        if mode == Mode.TESTING and self._state == SessionState.TESTING:
            self._state = SessionState.TESTING_DONE
            with common.sig:
                time.sleep(ANALYZER_SLEEP_SECONDS)
            self._server._ptd.stop()
            dirname = os.path.join(self._server._config.out_dir, self._id + "_testing")
            os.mkdir(dirname)
            with open(os.path.join(dirname, "spl.txt"), "w") as f:
                f.write(
                    read_log(self._server._config.ptd_logfile, self._id + "_testing")
                )
            return True

        # Unexpected state
        return False

    def upload(self, mode: Mode, fname: str) -> bool:
        if mode == Mode.RANGING and self._state == SessionState.RANGING_DONE:
            dirname = os.path.join(self._server._config.out_dir, self._id + "_ranging")
            with zipfile.ZipFile(fname, "r") as zf:
                zf.extractall(dirname)
            return True
        if mode == Mode.TESTING and self._state == SessionState.TESTING_DONE:
            dirname = os.path.join(self._server._config.out_dir, self._id + "_testing")
            with zipfile.ZipFile(fname, "r") as zf:
                zf.extractall(dirname)
            return True

        # Unexpected state
        return False

    def drop(self) -> None:
        try:
            if (
                self._state == SessionState.RANGING
                or self._state == SessionState.TESTING
            ):
                self._server._ptd.stop()
        finally:
            self._state = SessionState.DONE


def main() -> None:
    common.init("ptd-server")

    parser = argparse.ArgumentParser(description="Server for communication with PTD")

    # fmt: off
    parser.add_argument("-c", "--configurationFile", metavar="FILE", type=str, help="", default="server.conf")
    # fmt: on
    args = parser.parse_args()

    config = ServerConfig(args.configurationFile)

    common.mkdir_if_ne(config.out_dir)

    common.ntp_sync(config.ntp_server)

    server = Server(config)
    try:
        common.run_server(
            config.host,
            config.port,
            server.handle_connection,
        )
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
