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

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Tuple, Set, Any, Optional, Callable
import argparse
import json
import os
import re
import sys
import time
import uuid

current_dir = os.path.dirname(os.path.realpath(__file__))
ptd_client_server_dir = os.path.join(os.path.dirname(current_dir), "ptd_client_server")
sys.path.append(ptd_client_server_dir)


class LineWithoutTimeStamp(Exception):
    pass


from lib import source_hashes  # type: ignore

SUPPORTED_VERSION = ["1.9.1", "1.9.2"]
SUPPORTED_MODEL = {
    8: "YokogawaWT210",
    49: "YokogawaWT310",
    52: "YokogawaWT333E",
    77: "YokogawaWT333E",
}

RESULT_PATHS_C = [
    "client.log",
    "ranging/mlperf_log_accuracy.json",
    "ranging/mlperf_log_detail.txt",
    "ranging/mlperf_log_summary.txt",
    "ranging/mlperf_log_trace.json",
    "testing/mlperf_log_accuracy.json",
    "testing/mlperf_log_detail.txt",
    "testing/mlperf_log_summary.txt",
    "testing/mlperf_log_trace.json",
]

RESULT_PATHS_S = [
    "client.json",
    "client.log",
    "ptd_logs.txt",
    "ranging/spl.txt",
    "server.log",
    "testing/spl.txt",
]

RESULT_PATHS = RESULT_PATHS_C + RESULT_PATHS_S

RANGING_MODE = "ranging"
TESTING_NODE = "testing"


COMMON_ERROR = "Can't evaluate uncertainty of this sample!"
COMMON_WARNING = "Uncertainty unknown for the last measurement sample!"
DATE_REGEXP = "(^\d\d-\d\d-\d\d\d\d \d\d:\d\d:\d\d.\d\d\d)"
DATA_FORMAT = "%m-%d-%Y %H:%M:%S.%f"


class SessionDescriptor:
    def __init__(self, path: str):
        self.path = path
        with open(path, "r") as f:
            self.json_object: Dict = json.loads(f.read())
            self.required_fields_check()

    def required_fields_check(self) -> None:
        required_fields = [
            "version",
            "timezone",
            "modules",
            "sources",
            "messages",
            "uuid",
            "session_name",
            "results",
            "phases",
        ]
        absent_keys = set(required_fields) - self.json_object.keys()
        assert (
            len(absent_keys) == 0
        ), f"Required fields {', '.join(absent_keys)!r} does not exist in {self.path!r}"


def compare_dicts_values(d1: Dict[str, str], d2: Dict[str, str], comment: str) -> None:
    files_with_diff_check_sum = {k: d1[k] for k in d1 if k in d2 and d1[k] != d2[k]}
    assert len(files_with_diff_check_sum) == 0, f"{comment}" + "".join(
        [
            f"Expected {d1[i]}, but got {d2[i]} for {i}\n"
            for i in files_with_diff_check_sum
        ]
    )


def compare_dicts(s1: Dict[str, str], s2: Dict[str, str], comment: str) -> None:
    assert (
        s1.keys() == s2.keys()
    ), f"{comment} Expected files are {', '.join(s1.keys())!r}, but got {', '.join(s2.keys())!r}."

    compare_dicts_values(s1, s2, comment)


def sources_check(sd: SessionDescriptor, sources_path: Optional[str] = None) -> None:
    """Calculate sources checksums and compare them with sources checksums from the given json file."""
    s = sd.json_object["sources"]
    calc_s = source_hashes.get_sources_checksum(sources_path)
    compare_dicts(
        s,
        calc_s,
        f"{sd.path} 'sources' values and calculated {sources_path} content comparison:\n",
    )


def ptd_messages_check(sd: SessionDescriptor) -> None:
    """Performs multiple checks:
    - Check the version of the power meter.
    - Check the device model.
    - Compare message replies with expected values.
    - Check that initial values set after the test is completed.
    """
    msgs = sd.json_object["ptd_messages"]

    def get_ptd_answer(command: str) -> str:
        for msg in msgs:
            if msg["cmd"] == command:
                return msg["reply"]
        return ""

    identify_answer = get_ptd_answer("Identify")
    assert (
        len(identify_answer) != 0
    ), "There is no answer to the 'Identify' command for PTD."
    power_meter_model = identify_answer.split(",")[0]
    groups = re.search(r"(?<=version=)(.+?)-", identify_answer)
    version = "" if groups is None else groups.group(1)

    assert (
        version in SUPPORTED_VERSION
    ), f"PTD version {version!r} is not supported. Supported versions are 1.9.1 and 1.9.2"
    assert (
        power_meter_model in SUPPORTED_MODEL.values()
    ), f"Power meter {power_meter_model!r} is not supportable. Only {', '.join(SUPPORTED_MODEL.values())} are supported."

    def check_reply(cmd: str, reply: str) -> None:
        stop_counter = 0
        for msg in msgs:
            if msg["cmd"].startswith(cmd):
                if msg["cmd"] == "Stop":
                    # In normal flow the third answer to stop command is `Error: no measurement to stop`
                    if stop_counter == 2:
                        reply = "Error: no measurement to stop"
                    stop_counter += 1
                assert (
                    reply == msg["reply"]
                ), f"Wrong reply for {msg['cmd']!r} command. Expected {reply!r}, but got {msg['reply']!r}"

    check_reply("SR,A", "Range A changed")
    check_reply("SR,V", "Range V changed")
    check_reply(
        "Go,1000,",
        "Starting untimed measurement, maximum 500000 samples at 1000ms with 0 rampup samples",
    )
    check_reply("Stop", "Stopping untimed measurement")

    def get_initial_range(param_num: int, reply: str) -> str:
        reply_list = reply.split(",")
        try:
            if reply_list[param_num] == "0" and float(reply_list[param_num + 1]) > 0:
                return reply_list[param_num + 1]
        except (ValueError, IndexError) as e:
            raise Exception(f"Can not get power meters initial values from {reply!r}")
        return "Auto"

    def get_command_by_value_and_number(cmd: str, number: int) -> Optional[str]:
        command_counter = 0
        for msg in msgs:
            if msg["cmd"].startswith(cmd):
                command_counter += 1
                if command_counter == number:
                    return msg["cmd"]
        raise Exception(f"Can not find the {number} command starting with {cmd!r}.")
        return None

    initial_amps = get_initial_range(1, msgs[2]["reply"])
    initial_volts = get_initial_range(3, msgs[2]["reply"])

    initial_amps_command = get_command_by_value_and_number("SR,A", 3)
    initial_volts_command = get_command_by_value_and_number("SR,V", 3)

    assert (
        initial_amps_command == f"SR,A,{initial_amps}"
    ), f"Do not set Amps range as initial. Expected 'SR,A,{initial_amps}', got {initial_amps_command!r}."
    assert (
        initial_volts_command == f"SR,V,{initial_volts}"
    ), f"Do not set Volts range as initial. Expected 'SR,V,{initial_volts}', got {initial_volts_command!r}."


def uuid_check(client_sd: SessionDescriptor, server_sd: SessionDescriptor) -> None:
    """Compare UUIDs from client.json and server.json. They should be the same."""
    uuid_c = client_sd.json_object["uuid"]
    uuid_s = server_sd.json_object["uuid"]

    assert uuid.UUID(uuid_c["client"]) == uuid.UUID(
        uuid_s["client"]
    ), "'client uuid' is not equal."
    assert uuid.UUID(uuid_c["server"]) == uuid.UUID(
        uuid_s["server"]
    ), "'server uuid' is not equal."


def phases_check(client_sd: SessionDescriptor, server_sd: SessionDescriptor) -> None:
    """Check that the time difference between corresponding checkpoint values from client.json and server.json is less than 200 ms."""
    phases_ranging_c = client_sd.json_object["phases"]["ranging"]
    phases_testing_c = client_sd.json_object["phases"]["testing"]
    phases_ranging_s = server_sd.json_object["phases"]["ranging"]
    phases_testing_s = server_sd.json_object["phases"]["testing"]

    def comapre_time(phases_client, phases_server, mode) -> None:
        assert len(phases_client) == len(
            phases_server
        ), f"Phases amount is not equal for {mode} mode."
        for i in range(len(phases_client)):
            assert (
                abs(phases_client[i][0] - phases_server[i][0]) < 0.2
            ), f"The time difference for {i + 1} phase of {mode} mode is equal or more than 200ms."

    comapre_time(phases_ranging_c, phases_ranging_s, RANGING_MODE)
    comapre_time(phases_testing_c, phases_testing_s, TESTING_NODE)

    def compare_duration(range_duration: Decimal, test_duration: Decimal) -> None:
        duration_diff = abs(range_duration - test_duration) / max(
            range_duration, test_duration
        )
        duration_diff_percent = duration_diff * 100

        assert (
            duration_diff_percent < 5
        ), "Duration of ranging mode differs from the duration of testing mode by more than 5 percent"

    # Compare test duration using client.json and unix time.
    # It should be enough because phases values from client.json and server.json have not significant differences.
    ranging_duration = phases_ranging_c[2][0] - phases_ranging_c[1][0]
    testing_duration = phases_testing_c[2][0] - phases_testing_c[1][0]

    compare_duration(ranging_duration, testing_duration)

    ranging_duration = phases_ranging_c[2][1] - phases_ranging_c[1][1]
    testing_duration = phases_testing_c[2][1] - phases_testing_c[1][1]

    compare_duration(ranging_duration, testing_duration)

    ranging_duration = phases_ranging_s[2][1] - phases_ranging_s[1][1]
    testing_duration = phases_testing_s[2][1] - phases_testing_s[1][1]

    compare_duration(ranging_duration, testing_duration)


def session_name_check(
    client_sd: SessionDescriptor, server_sd: SessionDescriptor
) -> None:
    """Check that session names from client.json and server.json are equal."""
    session_name_c = client_sd.json_object["session_name"]
    session_name_s = server_sd.json_object["session_name"]
    assert (
        session_name_c == session_name_s
    ), f"Session name is not equal. Client session name is {session_name_c!r}. Server session name is {session_name_s!r}"


def messages_check(client_sd: SessionDescriptor, server_sd: SessionDescriptor) -> None:
    """Compare client and server messages list length.
       Compare messages values and replies from client.json and server.json.
       Compare client and server version.
    """
    mc = client_sd.json_object["messages"]
    ms = server_sd.json_object["messages"]

    assert (
        len(mc) == len(ms) - 1
    ), f"Client commands list length ({len(mc)}) should be less than server commands list length ({len(ms)}) by one. "

    # Check that server.json contains all client.json messages and replies.
    for i in range(len(mc)):
        assert (
            mc[i]["cmd"] == ms[i]["cmd"]
        ), f"Commands {i} are different. Server command is {ms[i]['cmd']!r}. Client command is {mc[i]['cmd']!r}."
        if "time" != mc[i]["cmd"]:
            assert (
                mc[i]["reply"] == ms[i]["reply"]
            ), f"Replies on command {mc[i]['cmd']!r} are different. Server reply is {ms[i]['reply']!r}. Client command is {mc[i]['reply']!r}."

    # Check client and server version from server.json. Server.json contains all client.json messages and replies. Checked earlier.
    def get_version(regexp: str, line: str) -> str:
        version_o = re.search(regexp, line)
        assert version_o is not None, f"Server version is not defined in:'{line}'"
        return version_o.group(1)

    client_version = get_version("mlcommons\/power client v(\d+)$", ms[0]["cmd"])
    server_version = get_version("mlcommons\/power server v(\d+)$", ms[0]["reply"])

    assert (
        client_version == server_version
    ), f"Client.py version ({client_version}) is not equal server.py version ({server_version})."


def results_check(
    server_sd: SessionDescriptor, client_sd: SessionDescriptor, result_path: str
) -> None:
    """Calculate the checksum for result files. Compare it with the checksums of the results from server.json.
       Compare results checksum from client.json and server.json.
       Check that results from client.json and server.json have no extra and absent files.
    """
    results = dict(source_hashes.hash_dir(result_path))
    results_s = server_sd.json_object["results"]
    results_c = client_sd.json_object["results"]

    results_without_server_json = results.copy()
    results_without_server_json.pop("server.json")

    compare_dicts(
        results_s,
        results_without_server_json,
        f"{server_sd.path} 'sources' checksum values and calculated {result_path} content checksum comparison:\n",
    )

    def result_files_compare(res, ref_res, path):
        extra_files = set(res.keys()) - set(ref_res)
        assert (
            len(extra_files) == 0
        ), f"There are extra files {', '.join(extra_files)!r} in the results of {path}"

        absent_files = set(ref_res) - set(res.keys())
        assert (
            len(absent_files) == 0
        ), f"There are absent files {', '.join(absent_files)!r} in the results of {path}"

    result_files_compare(results_s, RESULT_PATHS, server_sd.path)
    result_files_compare(results_c, RESULT_PATHS_C, client_sd.path)

    compare_dicts_values(
        results_c,
        results_s,
        f"{server_sd.path} and {client_sd.path} results checksum comparison",
    )


def check_ptd_logs(server_sd: SessionDescriptor, path: str) -> None:
    """Check if ptd message starts with 'WARNING' or 'ERROR' in ptd logs.
       Check 'Uncertainty checking for Yokogawa... is activated' in PTD logs.
    """
    start_ranging_time = None
    stop_ranging_time = None
    ranging_mark = f"{server_sd.json_object['session_name']}_ranging"

    with open(os.path.join(path, "ptd_logs.txt"), "r") as f:
        ptd_log_lines = f.readlines()

    def get_time(line: str) -> Decimal:
        log_time_str = re.search(DATE_REGEXP, line)
        if log_time_str and log_time_str.group(0):
            log_datetime = datetime.strptime(log_time_str.group(0), DATA_FORMAT)
            return Decimal(log_datetime.timestamp())

        raise LineWithoutTimeStamp(f"{line.strip()!r} in ptd_log.txt.")

    def find_common_problem(reg_exp: str, line: str, common_problem: str) -> None:
        problem_line = re.search(reg_exp, line)

        if problem_line and problem_line.group(0):
            log_time = get_time(line)
            if start_ranging_time is None or stop_ranging_time is None:
                raise Exception("Can not find ranging time in ptd_logs.txt.")
            if start_ranging_time < log_time < stop_ranging_time:
                assert (
                    problem_line.group(0).strip().startswith(common_problem)
                ), f"{line.strip()!r} in ptd_log.txt"
                return
            raise Exception(f"{line.strip()!r} in ptd_log.txt.")

    start_ranging_line = f": Go with mark {ranging_mark!r}"

    def get_msg_without_time(line: str) -> Optional[str]:
        try:
            get_time(line)
        except LineWithoutTimeStamp:
            return line
        msg_o = re.search(f"(?<={DATE_REGEXP}).+", line)
        if msg_o is None:
            return None
        return msg_o.group(0).strip()

    for line in ptd_log_lines:
        msg = get_msg_without_time(line)
        if msg is None:
            continue
        if (not start_ranging_time) and (start_ranging_line == msg):
            start_ranging_time = get_time(line)
        if (not stop_ranging_time) and bool(start_ranging_time):
            if ": Completed test" == msg:
                stop_ranging_time = get_time(line)
                break

    if start_ranging_time is None or stop_ranging_time is None:
        raise Exception("Can not find ranging time in ptd_logs.txt.")

    is_uncertainty_check_activated = False

    for line in ptd_log_lines:
        msg_o = re.search(f"Uncertainty checking for Yokogawa\S+ is activated", line)
        if msg_o is not None:
            try:
                log_time = None
                log_time = get_time(line)
            except LineWithoutTimeStamp:
                assert (
                    log_time is not None
                ), "ptd_logs.txt: Can not get timestamp for 'Uncertainty checking for Yokogawa... is activated' message."
            assert (
                start_ranging_time is not None and log_time < start_ranging_time
            ), "ptd_logs.txt: Uncertainty checking Yokogawa... was activated after ranging mode was started."
            is_uncertainty_check_activated = True
            break

    assert (
        is_uncertainty_check_activated
    ), "ptd_logs.txt: Line 'Uncertainty checking for Yokogawa... is activated' is not found."

    for line in ptd_log_lines:
        find_common_problem("(?<=WARNING:).+", line, COMMON_WARNING)
        find_common_problem("(?<=ERROR:).+", line, COMMON_ERROR)


def check_ptd_config(server_sd: SessionDescriptor) -> None:
    """Check the device number is supported.
       If the device is multichannel, check that two numbers are using for channel configuration.
    """
    ptd_config = server_sd.json_object["ptd_config"]

    dev_num = ptd_config["device_type"]
    assert dev_num in SUPPORTED_MODEL.keys(), (
        f"Device number {dev_num} is not supported. Supported numbers are "
        + ", ".join([str(i) for i in SUPPORTED_MODEL.keys()])
    )

    if dev_num == 77:
        channels = ""
        command = ptd_config["command"]

        for i in range(len(command)):
            if command[i] == "-c":
                channels = command[i + 1]
                break

        assert (
            len(channels.split(",")) == 2
            and ptd_config["channel"]
            and len(ptd_config["channel"]) == 2
        ), f"Expected multichannel mode for {SUPPORTED_MODEL[dev_num]}, but got 1-channel."


def check_with_logging(check_name: str, check: Callable[[], None]) -> bool:
    try:
        check()
    except Exception as e:
        print(f"[ ] {check_name}")
        print(f"\t{e}\n")
        return False
    else:
        print(f"[x] {check_name}")
    return True


def check(path: str, sources_path: str) -> int:
    client = SessionDescriptor(os.path.join(path, "client.json"))
    server = SessionDescriptor(os.path.join(path, "server.json"))

    check_with_description = {
        "Check client sources checksum": lambda: sources_check(client, sources_path),
        "Check server sources checksum": lambda: sources_check(server, sources_path),
        "Check PTD commands and replies": lambda: ptd_messages_check(server),
        "Check UUID": lambda: uuid_check(client, server),
        "Check session name": lambda: session_name_check(client, server),
        "Check time difference": lambda: phases_check(client, server),
        "Check client server messages": lambda: messages_check(client, server),
        "Check results checksum": lambda: results_check(server, client, path),
        "Check errors and warnings from PTD logs": lambda: check_ptd_logs(server, path),
        "Check PTD configuration": lambda: check_ptd_config(server),
    }

    result = True

    for description in check_with_description.keys():
        result &= check_with_logging(description, check_with_description[description])

    return 0 if result is True else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check PTD client-server session results"
    )
    parser.add_argument("session_directory", help="directory with stored data")
    parser.add_argument("sources_directory", help="sources directory")

    args = parser.parse_args()

    return_code = check(args.session_directory, args.sources_directory)

    exit(return_code)
