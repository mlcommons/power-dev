// Copyright 2018 The MLPerf Authors. All Rights Reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
// =============================================================================

#ifndef POWER_CLIENT_H
#define POWER_CLIENT_H

#include <stdio.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <string.h>
#include <algorithm>
#include <fstream>
#include <netinet/tcp.h>
#include <errno.h>
#include <iostream>
#include "./../cxxopts/include/cxxopts.hpp"
#include "clientConfigParser.h"
#include "maxAmpsVoltsParser.h"
#include <map>

#define START 100
#define START_LOG 200
#define STOP_LOG "300"
#define GET_FILE "500"

#define MODE_AMOUNT 2
#define MODE_RANGING 0

#define PYTHON_GET_MAX_VALUE "python getMaxValues.py -spl "
#define TMP_LOG_DIR "tmp"

#define DEFAULT_BUFFER_CHUNK_SIZE 4096
#define DEFAULT_FILE_CHUNK_SIZE 65536
#define DEFAULT_BUFLEN 512
#define WORKLOAD_NAME_SIZE 128

struct ServerAnswer {
    int code;
    char message[DEFAULT_BUFLEN];
};

struct StartLogMessage {
    int code;
    char workloadName[WORKLOAD_NAME_SIZE];
};

struct StartTestMessage {
    int code;
    int workloadAmount;
};

#endif //POWER_CLIENT_H