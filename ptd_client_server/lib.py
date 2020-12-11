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

from typing import Optional
import socketserver
import sys
import traceback
import logging


class Proto:
    _EOL = b"\r\n"
    # TODO: escape/unescape binary data?
    # TODO: b"\n" only (nc)

    def __init__(self, conn) -> None:
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


def run_server(host: str, port: int, handle) -> None:
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
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
        server.serve_forever()


def init(name: str) -> None:
    logging.basicConfig(
        level=logging.INFO, format=f"{name} %(asctime)s [%(levelname)s] %(message)s"
    )
