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
#include <errno.h>
#include <stdio.h>
#include <fcntl.h>
#include <sys/stat.h>

#pragma comment (lib, "Ws2_32.lib")

#define START_PTD 100
#define STOP_PTD 200
#define GET_DATA 500

#define PTD_PORT "8888"
#define PTD_IP "127.0.0.1"
#define MINUTE_DURATION_IN_SECONDS 60

#define DEFAULT_BUFFER_CHUNK_SIZE 4096
#define DEFAULT_FILE_CHUNK_SIZE 65536
#define DEFAULT_BUFLEN 512

struct serverAnswer {
    int code;
    char msg[DEFAULT_BUFLEN];
};

struct MaxAmpsVolts {
    float maxAmps;
    float maxVolts;
};

struct InitMessage {
    int messageNumber;
    MaxAmpsVolts maxValues;
};

#endif //POWER_SERVER_H
