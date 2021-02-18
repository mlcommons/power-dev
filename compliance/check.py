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
from typing import Dict, List, Tuple, Set, Any, Optional
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
    s = sd.json_object["sources"]
    calc_s = source_hashes.get_sources_checksum(sources_path)
    compare_dicts(
        s,
        calc_s,
        f"{sd.path} 'sources' values and calculated {sources_path} content comparison:\n",
    )


def ptd_messages_reply_check(sd: SessionDescriptor) -> None:
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


def uuid_check(client_sd: SessionDescriptor, server_sd: SessionDescriptor) -> None:
    uuid_c = client_sd.json_object["uuid"]
    uuid_s = server_sd.json_object["uuid"]

    assert uuid.UUID(uuid_c["client"]) == uuid.UUID(
        uuid_s["client"]
    ), "'client uuid' is not equal."
    assert uuid.UUID(uuid_c["server"]) == uuid.UUID(
        uuid_s["server"]
    ), "'server uuid' is not equal."


def phases_check(client_sd: SessionDescriptor, server_sd: SessionDescriptor) -> None:
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


def session_name_check(
    client_sd: SessionDescriptor, server_sd: SessionDescriptor
) -> None:
    session_name_c = client_sd.json_object["session_name"]
    session_name_s = server_sd.json_object["session_name"]
    assert (
        session_name_c == session_name_s
    ), f"Session name is not equal. Client session name is {session_name_c!r}. Server session name is {session_name_s!r}"


def messages_check(client_sd: SessionDescriptor, server_sd: SessionDescriptor) -> None:
    mc = client_sd.json_object["messages"]
    ms = server_sd.json_object["messages"]

    for i in range(len(mc)):
        assert (
            mc[i]["cmd"] == ms[i]["cmd"]
        ), f"Commands {i} are different. Server command is {ms[i]['cmd']!r}. Client command is {mc[i]['cmd']!r}."
        if "time" != mc[i]["cmd"]:
            assert (
                mc[i]["reply"] == ms[i]["reply"]
            ), f"Replies on command {mc[i]['cmd']!r} are different. Server reply is {ms[i]['reply']!r}. Client command is {mc[i]['reply']!r}."


def results_check(
    server_sd: SessionDescriptor, client_sd: SessionDescriptor, result_path: str
) -> None:
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
                ), "ptd_logs.txt check. Can not get timestamp for 'Uncertainty checking for Yokogawa... is activated' message."
            assert (
                start_ranging_time is not None and log_time < start_ranging_time
            ), "ptd_logs.txt check. Uncertainty checking Yokogawa... was activated after ranging mode was started."
            is_uncertainty_check_activated = True
            break

    assert (
        is_uncertainty_check_activated
    ), "ptd_logs.txt check. Line 'Uncertainty checking for Yokogawa... is activated' is not found."

    for line in ptd_log_lines:
        find_common_problem("(?<=WARNING:).+", line, COMMON_WARNING)
        find_common_problem("(?<=ERROR:).+", line, COMMON_ERROR)


def check_ptd_config(server_sd: SessionDescriptor) -> None:
    dev_num = server_sd.json_object["ptd_config"]["device_type"]
    assert dev_num in SUPPORTED_MODEL.keys(), (
        f"Device number {dev_num} is not supported. Supported numbers are "
        + ", ".join([str(i) for i in SUPPORTED_MODEL.keys()])
    )


def check(path: str, sources_path: str) -> None:
    client = SessionDescriptor(os.path.join(path, "client.json"))
    server = SessionDescriptor(os.path.join(path, "server.json"))

    sources_check(client, sources_path)
    sources_check(server, sources_path)
    ptd_messages_reply_check(server)
    uuid_check(client, server)
    phases_check(client, server)
    session_name_check(client, server)
    messages_check(client, server)
    results_check(server, client, path)
    check_ptd_logs(server, path)
    check_ptd_config(server)
    print("Results of the test are consistent")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check PTD client-server session results"
    )
    parser.add_argument("session_directory", help="directory with stored data")
    parser.add_argument("sources_directory", help="sources directory")

    args = parser.parse_args()

    check(args.session_directory, args.sources_directory)
