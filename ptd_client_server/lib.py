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
import string
import subprocess
import sys


class Proto:
    _EOL = b"\r\n"
    # TODO: escape/unescape binary data?
    # TODO: b"\n" only (nc)

    def __init__(self, conn: socket.socket) -> None:
        self._buf = b""
        self._x: Optional[socket.socket] = conn

    def recv(self) -> Optional[str]:
        if self._x is None:
            return None
        while self._EOL not in self._buf:
            recvd = self._x.recv(1024 * 16)
            if len(recvd) == 0:
                self._close()
                return None
            self._buf += recvd

        idx = self._buf.index(self._EOL)
        result = self._buf[:idx]
        self._buf = self._buf[idx + len(self._EOL) :]
        return result.decode(errors="replace")

    def send(self, data: str) -> None:
        if self._x is None:
            return
        self._x.sendall(data.encode() + self._EOL)

    def command(self, data: str) -> Optional[str]:
        if self._x is None:
            return None
        self.send(data)
        return self.recv()

    def recv_file(self, filename: str) -> None:
        with open(filename + ".tmp", "wb") as f:
            try:
                while True:
                    line = self.recv()
                    if line is None:
                        raise Exception(
                            "Remote peer disconnected while sending a file {filename!r}"
                        )

                    chunk_len = int(line, 10)
                    if chunk_len < 0:
                        raise ValueError("Negative chunk length")

                    if chunk_len == 0:
                        break

                    data = self._recv_len(chunk_len)
                    if data is None:
                        raise Exception(
                            "Remote peer disconnected while sending a file {filename!r}"
                        )

                    f.write(data)
            except:
                self._close()
                raise
        os.rename(filename + ".tmp", filename)

    def send_file(self, filename: str) -> None:
        with open(filename, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                self.send(str(len(chunk)))
                if len(chunk) == 0:
                    break
                if self._x is not None:
                    self._x.sendall(chunk)
                else:
                    break

    def _recv_len(self, length: int) -> Optional[bytes]:
        if self._x is None:
            return None
        result = b""
        while length > 0:
            if len(self._buf) > 0:
                len2 = min(length, len(self._buf))
                result += self._buf[:len2]
                self._buf = self._buf[len2:]
                length -= len2
            else:
                recvd = self._x.recv(min(1024 * 16, length))
                if len(recvd) == 0:
                    self._close()
                    return None
                result += recvd
                length -= len(recvd)
        return result

    def _close(self) -> None:
        if self._x is not None:
            self._x.close()
            self._x = None


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


def check_label(label: str) -> bool:
    valid_chars = "-_" + string.ascii_letters + string.digits
    return label != "" and all((c in valid_chars for c in label))


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
