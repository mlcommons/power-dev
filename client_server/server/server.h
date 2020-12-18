//
// Created by julia on 04/12/2020.
//

#ifndef POWER_SERVER_H
#define POWER_SERVER_H
#undef UNICODE

#define WIN32_LEAN_AND_MEAN

#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <stdlib.h>
#include <stdio.h>
#include <tlhelp32.h>
#include <tchar.h>
#include <iostream>
#include <processthreadsapi.h>
#include <stdlib.h>
#include <algorithm>
#include <fstream>
#include <netinet/tcp.h>
#include "./../cxxopts/include/cxxopts.hpp"
#include "./../serverConfigParserHelper/serverConfigParser.h"
#include "./../sending_file/sending_file.h"
#include "./../interacting_with_process/interacting_with_process.h"
#include "./../maxValues/maxAmpsVoltsParser.h"
#include <errno.h>
#include <filesystem>
#include <stdio.h>
#include <fcntl.h>
#include <sys/stat.h>

#pragma comment (lib, "Ws2_32.lib")

#define START 100
#define START_LOG 200
#define STOP_LOG 300

#define SLEEP_PTD_AFTER_CHANGING_RANGE 10000

#define PTD_PORT "8888"
#define PTD_IP "127.0.0.1"
#define MINUTE_DURATION_IN_SECONDS 60

#define DEFAULT_BUFLEN 512
#define FILE_NAME 128

#define MODE_AMOUNT 2
#define MODE_RANGING 0
#define MODE_TESTING 1

#define MAX_AMPS_VOLTS_VALUE_FILE "./maxAmpsVoltsValue.json"
#define MAX_AMPS_VOLTS_VALUE_SCRIPT "python.exe getMaxValues.py -spl"

struct serverAnswer {
    int code;
    char msg[DEFAULT_BUFLEN];
};

struct StartLogMessage {
    int code;
    char workloadName[FILE_NAME];
};

struct StartTestMessage {
    int code;
    int workloadAmount;
};

#endif //POWER_SERVER_H