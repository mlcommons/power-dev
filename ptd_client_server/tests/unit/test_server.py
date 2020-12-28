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

import pytest

from lib import server


def test_parse_listen() -> None:
    with pytest.raises(ValueError):
        server.get_host_port_from_listen_string("badaddress 1234")

    with pytest.raises(ValueError):
        server.get_host_port_from_listen_string("127.0.0.1")

    assert server.get_host_port_from_listen_string("127.0.0.1 1234") == (
        "127.0.0.1",
        1234,
    )

    assert server.get_host_port_from_listen_string("2001:db8::8a2e:370:7334 1234") == (
        "2001:db8::8a2e:370:7334",
        1234,
    )
