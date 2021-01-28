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

from pathlib import Path
import json
import shutil
import subprocess
import sys


def test_foo(tmp_path: Path) -> None:
    shutil.copytree(Path(__file__).parent.parent.parent / "lib", tmp_path / "lib")
    with open(tmp_path / "main.py", "wb") as f:
        f.write(
            b"from lib import source_hashes\n"
            b"import json\n"
            b"source_hashes.init()\n"
            b"print(json.dumps(source_hashes.get()))\n"
        )

    results = []

    results.append(
        subprocess.check_output(
            [sys.executable, str(tmp_path / "main.py")],
            cwd="C:\\" if sys.platform == "win32" else "/",
        )
    )
    results.append(
        subprocess.check_output(
            [sys.executable, "main.py"],
            cwd=tmp_path,
        )
    )
    results.append(
        subprocess.check_output(
            [sys.executable, "./main.py"],
            cwd=tmp_path,
        )
    )
    if sys.platform == "win32":
        results.append(
            subprocess.check_output(
                [sys.executable, ".\\main.py"],
                cwd=tmp_path,
            )
        )

    for result in results[1:]:
        assert results[0] == result

    parsed_result = json.loads(results[0])
    assert "sources" in parsed_result
    assert "modules" in parsed_result
    assert "main.py" in parsed_result["sources"]
    assert "lib/source_hashes.py" in parsed_result["sources"]
