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
from pathlib import Path
from typing import Any, Callable, Optional, Dict, Tuple, List, Set
import argparse
import atexit
import configparser
import datetime
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import zipfile

from . import common
from . import time_sync


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


def tcp_port_is_occupied(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)
        return s.connect_ex(("127.0.0.1", port)) == 0


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

        _UNSET = object()
        used: Dict[str, Set[str]] = {}

        def get(
            section: str,
            option: str,
            parse: Optional[Callable[[str], Any]] = None,
            fallback: Any = _UNSET,
        ) -> Any:
            used.setdefault(section.lower(), set()).add(option.lower())
            if fallback is _UNSET:
                try:
                    val = conf.get(section, option)
                except configparser.Error as e:
                    exit_with_error_msg(f"{filename}: config error: {e}")
            else:
                val = conf.get(section, option, fallback=fallback)

            if parse is not None and isinstance(val, str):
                try:
                    return parse(val)
                except Exception:
                    logging.exception(
                        f"{filename}: could not parse option {option!r} in {section!r}"
                    )
                    exit(1)
            else:
                return val

        self.ntp_server: str = get("server", "ntpServer")
        self.out_dir: str = get("server", "outDir")
        self.host: str
        self.port: int
        self.host, self.port = get(
            "server",
            "listen",
            parse=get_host_port_from_listen_string,
            fallback=f"0.0.0.0 {common.DEFAULT_PORT}",
        )

        channel: int = get("ptd", "channel", parse=int, fallback=None)
        ptd_device_type: int = get("ptd", "deviceType", parse=int)
        ptd_interface_flag: str = get("ptd", "interfaceFlag")
        # TODO: validate ptd_interface_flag?
        # TODO: validate ptd_device_type?
        self.ptd_logfile: str = get("ptd", "logfile")
        self.ptd_port: int = get("ptd", "networkPort", parse=int, fallback="8888")
        self.ptd_command: List[str] = [
            get("ptd", "ptd"),
            "-l",
            self.ptd_logfile,
            "-p",
            str(self.ptd_port),
            *([] if channel is None else ["-c", f"{channel}"]),
            *([] if ptd_interface_flag == "" else [ptd_interface_flag]),
            str(ptd_device_type),
            get("ptd", "devicePort"),
        ]

        for section, used_items in used.items():
            unused_options = conf[section].keys() - set((i.lower() for i in used_items))
            if len(unused_options) != 0:
                logging.warning(
                    f"{filename}: ignoring unknown options in section {section!r}: "
                    f"{', '.join(unused_options)}"
                )

        unused_sections = set(conf.sections()) - {"server", "ptd"}
        if len(unused_sections) != 0:
            logging.warning(
                f"{filename}: ignoring unknown sections: {', '.join(unused_sections)}"
            )

        # Check configurtion
        self._check(filename)

    def _check(self, filename: str) -> None:
        path = Path(self.ptd_logfile)
        if not (path.parent.exists()):
            exit_with_error_msg(
                f"{filename}: {str(path.parent)!r} does not exist. Please create {str(path.parent)!r} folder."
            )

        if tcp_port_is_occupied(self.ptd_port):
            exit_with_error_msg(
                f"The PTDaemon port {self.ptd_port} is already occupied."
            )


class Ptd:
    def __init__(self, command: List[str], port: int, log_dir_path: str) -> None:
        self._process: Optional[subprocess.Popen[Any]] = None
        self._socket: Optional[socket.socket] = None
        self._proto: Optional[common.Proto] = None
        self._command = command
        self._port = port
        self._init_Amps: Optional[str] = None
        self._init_Volts: Optional[str] = None
        atexit.register(self._force_terminate)
        self._tee: Optional[Tee] = None
        self._log_dir_path = log_dir_path

    def start(self) -> None:
        try:
            self._start()
        except Exception:
            logging.exception("Could not start PTDaemon")
            exit(1)

    def _start(self) -> None:
        if self._process is not None:
            return
        if tcp_port_is_occupied(self._port):
            raise RuntimeError(f"The PTDaemon port {self._port} is already occupied")
        logging.info(f"Running PTDaemon: {self._command}")

        self._tee = Tee(os.path.join(self._log_dir_path, "ptd_logs.txt"))
        if sys.platform == "win32":
            # creationflags=subprocess.CREATE_NEW_PROCESS_GROUP:
            #   We do not want to pass ^C from the current console to the
            #   PTDaemon.  Instead, we terminate it explicitly in self.terminate().
            self._process = subprocess.Popen(
                self._command,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                bufsize=1,
                universal_newlines=True,
                stdout=self._tee.w,
                stderr=subprocess.STDOUT,
            )
        else:
            self._process = subprocess.Popen(
                self._command,
                bufsize=1,
                universal_newlines=True,
                stdout=self._tee.w,
                stderr=subprocess.STDOUT,
            )
        self._tee.started()

        retries = 100
        s = None
        while s is None and retries > 0:
            if self._process is not None and self._process.poll() is not None:
                raise RuntimeError("PTDaemon unexpectedly terminated")
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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

        if self._tee is not None:
            self._tee.done()
            self._tee = None

    def _force_terminate(self) -> None:
        if self._process is not None:
            logging.info("Force stopping ptd...")
            self._process.kill()
            self._process.wait()
        self._process = None

        if self._tee is not None:
            self._tee.done()
            self._tee = None

    def cmd(self, cmd: str) -> Optional[str]:
        if self._proto is None:
            return None
        if self._process is None or self._process.poll() is not None:
            exit_with_error_msg("PTDaemon unexpectedly terminated")
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
        self._stop = False

    def handle_connection(self, p: common.Proto) -> None:
        p.enable_keepalive()

        with common.sig:
            # TODO: timeout and max msg size for recv
            magic = p.recv()
        p.send(common.MAGIC_SERVER)
        if magic != common.MAGIC_CLIENT:
            logging.error(
                f"Handshake failed, expected {common.MAGIC_CLIENT!r}, got {magic!r}"
            )
            return

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

            if self._stop:
                logging.info("Stopping the server")
                exit(0)

    def _handle_cmd(self, cmd: str, p: common.Proto) -> str:
        cmd = cmd.split(",")
        if len(cmd) == 0:
            return "..."
        if cmd[0] == "time":
            return str(time.time())
        if cmd[0] == "set_ntp":
            time_sync.set_ntp(self._config.ntp_server)
            return "OK"
        if cmd[0] == "stop":
            logging.info("The server will be stopped after processing this client")
            self._stop = True
            return "OK"
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
                        logging.info(f"Removed {fname!r}")
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
        self._drop_session()


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


class Tee:
    def __init__(self, fname: str) -> None:
        self._closed = False
        self._r, self.w = os.pipe()
        self._f = open(fname, "w")
        self._thread = threading.Thread(target=self._run)
        self._thread.daemon = True
        self._thread.start()

    def started(self) -> None:
        """Should be called passing self.w to Popen()"""
        if not self._closed:
            os.close(self.w)
            self._closed = True

    def done(self) -> None:
        """Should be called after Popen.wait()"""
        if not self._closed:
            os.close(self.w)
            self._closed = True
        self._thread.join()

    def _run(self) -> None:
        try:
            while True:
                rd = os.read(self._r, 1024)
                if len(rd) == 0:
                    break
                rd_str = rd.decode(errors="ignore")
                sys.stderr.write(rd_str)
                sys.stderr.flush()
                self._f.write(rd_str)
        finally:
            self._f.close()
            os.close(self._r)


class Session:
    def __init__(self, server: Server, label: str) -> None:
        self._server: Server = server
        self._go_command_time: Optional[float] = None
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._id: str = timestamp + "_" + label if label != "" else timestamp
        self.log_dir_path = os.path.join(self._server._config.out_dir, self._id)
        os.mkdir(self.log_dir_path)
        self._ptd = Ptd(
            server._config.ptd_command, server._config.ptd_port, self.log_dir_path
        )

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
            self._ptd.start()
            self._ptd.cmd("SR,V,Auto")
            self._ptd.cmd("SR,A,Auto")
            with common.sig:
                time.sleep(ANALYZER_SLEEP_SECONDS)
            logging.info("Starting ranging mode")
            self._ptd.cmd(f"Go,1000,0,{self._id}_ranging")
            self._go_command_time = time.monotonic()

            self._state = SessionState.RANGING

            return True

        if mode == Mode.TESTING and self._state == SessionState.RANGING_DONE:
            self._ptd.start()
            self._ptd.cmd(f"SR,V,{self._maxVolts}")
            self._ptd.cmd(f"SR,A,{self._maxAmps}")
            with common.sig:
                time.sleep(ANALYZER_SLEEP_SECONDS)
            logging.info("Starting testing mode")
            self._ptd.cmd(f"Go,1000,0,{self._id}_testing")

            self._state = SessionState.TESTING

            return True

        # Unexpected state
        return False

    def stop(self, mode: Mode) -> bool:
        if mode == Mode.RANGING and self._state == SessionState.RANGING_DONE:
            return True
        if mode == Mode.TESTING and self._state == SessionState.TESTING_DONE:
            return True

        with common.sig:
            time.sleep(ANALYZER_SLEEP_SECONDS)

        # TODO: handle exceptions?

        if mode == Mode.RANGING and self._state == SessionState.RANGING:
            self._state = SessionState.RANGING_DONE
            self._ptd.stop()
            assert self._go_command_time is not None
            test_duration = time.monotonic() - self._go_command_time
            dirname = os.path.join(self.log_dir_path, "ranging")
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
            self._ptd.stop()
            dirname = os.path.join(self.log_dir_path, "testing")
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
            dirname = os.path.join(self.log_dir_path, "ranging")
            return self._extract(fname, dirname)
        if mode == Mode.TESTING and self._state == SessionState.TESTING_DONE:
            dirname = os.path.join(self.log_dir_path, "testing")
            return self._extract(fname, dirname)

        # Unexpected state
        return False

    def drop(self) -> None:
        self._ptd.terminate()
        self._state = SessionState.DONE

    def _extract(self, fname: str, dirname: str) -> bool:
        try:
            with zipfile.ZipFile(fname, "r") as zf:
                zf.extractall(dirname)
            logging.info(f"Extracted {fname!r} into {dirname!r}")
            return True
        except Exception:
            logging.exception(
                f"Got an exception while extracting {fname!r} into {dirname!r}"
            )

        return False


def main() -> None:
    common.init("ptd-server")

    common.system_check()

    parser = argparse.ArgumentParser(description="Server for communication with PTD")
    required = parser.add_argument_group("required arguments")

    # fmt: off
    required.add_argument("-c", "--configurationFile", metavar="FILE", type=str, help="", required=True)
    # fmt: on
    args = parser.parse_args()

    config = ServerConfig(args.configurationFile)

    common.mkdir_if_ne(config.out_dir)

    if not time_sync.ntp_sync(config.ntp_server):
        exit_with_error_msg("Could not synchronize with NTP")

    common.log_sources()

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
