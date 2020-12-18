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

from typing import Callable, Optional
import logging
import os
import socket
import socketserver
import subprocess
import sys


class Proto:
    _EOL = b"\r\n"
    # TODO: escape/unescape binary data?
    # TODO: b"\n" only (nc)

    def __init__(self, conn: socket.socket) -> None:
        self._buf = b""
        self._x = conn

    def recv(self) -> Optional[str]:
        while self._EOL not in self._buf:
            recvd = self._x.recv(1024 * 16)
            if len(recvd) == 0:
                return None
            self._buf += recvd

        idx = self._buf.index(self._EOL)
        result = self._buf[:idx]
        self._buf = self._buf[idx + len(self._EOL) :]
        return result.decode(errors="replace")

    def send(self, data: str) -> None:
        self._x.sendall(data.encode() + self._EOL)

    def command(self, data: str) -> Optional[str]:
        self.send(data)
        return self.recv()


def run_server(host: str, port: int, handle: Callable[[Proto], None]) -> None:
    class Handler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            logging.info(f"Connected {self.client_address}")
            p = Proto(self.request)
            try:
                handle(p)
            except KeyboardInterrupt as e:
                raise e
            except:
                logging.exception("Got an exception")
            logging.info("Done processing")

    class Server(socketserver.TCPServer):
        allow_reuse_address = True

    with Server((host, port), Handler) as server:
        logging.info(f"Ready to accept connections at {host}:{port}")
        server.serve_forever()


def init(name: str) -> None:
    logging.basicConfig(
        level=logging.INFO, format=f"{name} %(asctime)s [%(levelname)s] %(message)s"
    )


def ntp_sync(server: Optional[str]) -> None:
    if server == "" or server is None:
        logging.info("No NTP server configured. Skipping NTP sync.")
        return

    logging.info(f"Synchronizing with {server!r} time using NTP...")

    if sys.platform == "win32":
        try:
            subprocess.run("w32tm /register", check=True)

            # Do not check for the error: it may be already running.
            subprocess.run("net start w32time")

            subprocess.run(
                [
                    "w32tm",
                    "/config",
                    "/syncfromflags:manual",
                    "/update",
                    f"/manualpeerlist:{server},0x8",
                ],
                check=True,
            )

            subprocess.run("w32tm /resync", check=True)

            logging.info("w32tm /stripchart output:")
            subprocess.run(
                [
                    "w32tm",
                    "/stripchart",
                    "/dataonly",
                    "/samples:1",
                    f"/computer:{server}",
                ],
                check=True,
            )
        except Exception:
            logging.error("Could not sync time using windows time service.")
            raise
    else:
        command = ["ntpdate", "-b", "--", server]
        if os.getuid() != 0:
            command = ["sudo", "-n"] + command

        try:
            subprocess.run(command, input="", check=True)
        except Exception:
            logging.error("Could not sync time using ntpd.")
            raise
