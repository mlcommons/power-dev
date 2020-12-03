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

int sentMessage(int ClientSocket, char *message, size_t msgLength) {
    int iSendResult = send(ClientSocket, message, msgLength, 0);
    if (iSendResult == SOCKET_ERROR) {
        std::cerr << "Send failed with error: " << WSAGetLastError() << "Exit (1)" << std::endl;
        closesocket(ClientSocket);
        WSACleanup();
        return 1;
    }

    return 0;
}

int sentAnswerForClient(int ClientSocket, serverAnswer *answer) {
    sentMessage(ClientSocket, (char *) answer, sizeof(serverAnswer));
    std::cout << "Send message to client: code is " << answer->code << ", " << "message is " << answer->msg
              << std::endl;
    return 0;
}

int sentAnswer(int ClientSocket, int code, char *msg) {
    serverAnswer answer;
    answer.code = code;
    sprintf(answer.msg, msg);
    return sentAnswerForClient(ClientSocket, &answer);
}

int64_t GetFileSize(const std::string &fileName) {
    FILE *f;
    if ((f = fopen(fileName.c_str(), "rb")) == NULL) {
        return -1;
    }
    fseek(f, 0, SEEK_END);
    const int64_t len = ftell(f);
    fclose(f);
    return len;
}

int SendBuffer(SOCKET s, const char *buffer, int bufferSize, int chunkSize = DEFAULT_BUFFER_CHUNK_SIZE) {
    int allSendedBytes = 0;
    while (allSendedBytes < bufferSize) {
        const int sendedBytes = send(s, &buffer[allSendedBytes], std::min(chunkSize, bufferSize - allSendedBytes), 0);
        if (sendedBytes < 0) {
            return sendedBytes;
        }
        allSendedBytes += sendedBytes;
    }
    return allSendedBytes;
}

int64_t SendFile(SOCKET s, const std::string &fileName, int chunkSize = DEFAULT_FILE_CHUNK_SIZE) {
    const int64_t fileSize = GetFileSize(fileName);

    if (fileSize < 0) {
        std::cerr << "Can not get file size" << std::endl;
        return 1;
    }

    std::ifstream file(fileName, std::ifstream::binary);
    if (file.fail()) {
        std::cerr << "Can not open ifstream" << std::endl;
        return 1;
    }

    // Send file size
    if (SendBuffer(s, reinterpret_cast<const char *>(&fileSize),
                   sizeof(fileSize)) != sizeof(fileSize)) {
        std::cerr << "Can not send file size" << std::endl;
        return 1;
    }

    char *buffer = new char[chunkSize];
    bool errored = false;
    int64_t i = fileSize;
    while (i != 0) {
        const int64_t ssize = std::min(i, (int64_t) chunkSize);
        if (!file.read(buffer, ssize)) {
            errored = true;
            break;
        }
        const int l = SendBuffer(s, buffer, (int) ssize);
        if (l < 0) {
            errored = true;
            break;
        }
        i -= l;
    }
    delete[] buffer;
    if (!errored) {
        std::cout << "Send file to client" << std::endl;
    } else {
        std::cerr << "Can not send file to client" << std::endl;
    }

    file.close();

    return errored ? 1 : fileSize;
}

bool executeSystemCommand(char *command_Line, STARTUPINFO *si, PROCESS_INFORMATION *pi) {
    ZeroMemory(si, sizeof(*si));
    si->cb = sizeof(si);
    ZeroMemory(pi, sizeof(*pi));

    // Start the child process.
    if (!CreateProcess(NULL,   // No module name (use command line)
                       command_Line,        // Command line
                       NULL,           // Process handle not inheritable
                       NULL,           // Thread handle not inheritable
                       FALSE,          // Set handle inheritance to FALSE
                       CREATE_NEW_CONSOLE, // No creation flags
                       NULL,           // Use parent's environment block
                       NULL,           // Use parent's starting directory
                       si,            // Pointer to STARTUPINFO structure
                       pi)           // Pointer to PROCESS_INFORMATION structure
            ) {
        std::cerr << "CreateProcess failed " << GetLastError() << "Exit (1)" << std::endl;
        return (false);
    }
    return (true);
}

bool closeSystemProcess(PROCESS_INFORMATION *pi) {
    return TerminateProcess(pi->hProcess, 0) && CloseHandle(pi->hProcess) && CloseHandle(pi->hThread);
}

void recvPtdAnswer(int ptdClientSocket) {
    char recvbuf[DEFAULT_BUFLEN];
    int iResult = recv(ptdClientSocket, recvbuf, DEFAULT_BUFLEN, 0);
    if (iResult > 0) {
        recvbuf[iResult] = '\0';
        std::cout << "PTD answer: " << recvbuf << std::endl;
    } else if (iResult == 0)
        std::cout << "Connection closed" << std::endl;
    else
        std::cout << "\"recv failed with error:" << WSAGetLastError() << std::endl;
}

int startPtdClient() {
    WSADATA wsaData;
    SOCKET ConnectSocket = INVALID_SOCKET;
    struct addrinfo *result = NULL,
            hints, ServerAddress;
    int iResult;

    // Initialize Winsock
    iResult = WSAStartup(MAKEWORD(2, 2), &wsaData);
    if (iResult != 0) {
        std::cerr << "WSAStartup failed with error: " << iResult << std::endl;
        return -1;
    }

    ZeroMemory(&hints, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    // Resolve the server address and port
    iResult = getaddrinfo(PTD_IP, PTD_PORT, &hints, &result);
    if (iResult != 0) {
        std::cerr << "getaddrinfo failed with error: " << iResult << std::endl;
        WSACleanup();
        return -1;
    }
    // Attempt to connect to an address until one succeeds
    // Create a SOCKET for connecting to server
    ConnectSocket = socket(AF_INET, SOCK_STREAM, 0);
    if (ConnectSocket == INVALID_SOCKET) {
        std::cerr << "socket failed with error: " << WSAGetLastError() << std::endl;
        WSACleanup();
        return -1;
    }

    // Connect to PTD.
    sockaddr_in clientService;
    clientService.sin_family = AF_INET;
    clientService.sin_addr.s_addr = inet_addr(PTD_IP);
    clientService.sin_port = htons(atoi(PTD_PORT));

    int i = 0;
    //Waiting connection for PTD for one minute
    while (i < MINUTE_DURATION_IN_SECONDS) {
        iResult = connect(ConnectSocket, (SOCKADDR *) &clientService, sizeof(clientService));
        if (iResult != SOCKET_ERROR) {
            break;
        }
        i++;
        Sleep(1000);
    }

    if (iResult == SOCKET_ERROR) {
        closesocket(ConnectSocket);
        ConnectSocket = INVALID_SOCKET;
    }

    freeaddrinfo(result);

    if (ConnectSocket == INVALID_SOCKET) {
        std::cerr << "Unable to connect to PTD!" << std::endl;
        WSACleanup();
        return -1;
    }
    char identifyCommand[] = "Identify\r\n";
    sentMessage(ConnectSocket, identifyCommand, strlen(identifyCommand));
    recvPtdAnswer(ConnectSocket);

    return ConnectSocket;
}

int __cdecl main(int argc, char const *argv[]) {
    char ptdSetAmps[] = "SR,A,Auto\r\n";
    char ptdSetVolts[] = "SR,V,Auto\r\n";
    char ptdGo[] = "Go,1000,0\r\n";
    char ptdStop[] = "Stop\r\n";

    cxxopts::Options options("Server for communication with PTD", "A brief description");

    options.add_options()
            ("p,serverPort", "Server port", cxxopts::value<std::string>()->default_value("4950"))
            ("i,ipAddress", "Server ip address", cxxopts::value<std::string>())
            ("c,ptdConfigurationFile", "PTD configuration file path",
             cxxopts::value<std::string>()->default_value("config.txt"))
            ("h,help", "Print usage");

    auto parserResult = options.parse(argc, argv);

    if (parserResult.count("help")) {
        std::cout << options.help() << std::endl;
        exit(0);
    }

    std::string serverIpAddress;
    if (parserResult.count("ipAddress")) {
        serverIpAddress = parserResult["ipAddress"].as<std::string>();
    } else {
        std::cout << "Server ip address is required" << std::endl;
        return 1;
    }

    std::string serverPort = parserResult["serverPort"].as<std::string>();
    std::string configurationFile = parserResult["ptdConfigurationFile"].as<std::string>();
    ServerCommands commands = getServerCommands(configurationFile);

    WSADATA wsaData;
    int iResult;

    SOCKET ListenSocket = INVALID_SOCKET;
    SOCKET ClientSocket = INVALID_SOCKET;

    struct addrinfo *result = NULL;
    struct addrinfo hints;

    char recvbuf[DEFAULT_BUFLEN];
    int recvbuflen = DEFAULT_BUFLEN;

    // Initialize Winsock
    iResult = WSAStartup(MAKEWORD(2, 2), &wsaData);
    if (iResult != 0) {
        std::cerr << "WSAStartup failed with error: " << iResult << "Exit (1)" << std::endl;
        return 1;
    }
    STARTUPINFO siNtp;
    PROCESS_INFORMATION piNtp;

    char ntpCommand[commands.ntp.length()];
    for (int i = 0; i < commands.ntp.length(); i++) {
        ntpCommand[i] = commands.ntp[i];
    }

    executeSystemCommand(ntpCommand, &siNtp, &piNtp);

    ZeroMemory(&hints, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;
    hints.ai_flags = AI_PASSIVE;

    // Resolve the server address and port
    iResult = getaddrinfo(serverIpAddress.c_str(), serverPort.c_str(), &hints, &result);
    if (iResult != 0) {
        std::cerr << "getaddrinfo failed with error: " << iResult << "Exit (1)" << std::endl;
        WSACleanup();
        return 1;
    }

    // Create a SOCKET for connecting to server
    ListenSocket = socket(result->ai_family, result->ai_socktype, result->ai_protocol);
    if (ListenSocket == INVALID_SOCKET) {
        std::cerr << "getaddrinfo failed with error: " << WSAGetLastError() << "Exit (1)" << std::endl;
        freeaddrinfo(result);
        WSACleanup();
        return 1;
    }

    // Setup the TCP listening socket
    iResult = bind(ListenSocket, result->ai_addr, (int) result->ai_addrlen);
    if (iResult == SOCKET_ERROR) {
        std::cerr << "bind failed with error: " << WSAGetLastError() << "Exit (1)" << std::endl;
        freeaddrinfo(result);
        closesocket(ListenSocket);
        WSACleanup();
        return 1;
    }

    freeaddrinfo(result);

    // Accept a client socket
    iResult = listen(ListenSocket, 1);
    if (iResult == SOCKET_ERROR) {
        std::cerr << "listen failed with error: " << WSAGetLastError() << "Exit (1)" << std::endl;
        closesocket(ListenSocket);
        WSACleanup();
        return 1;
    }
    int ptdClientSocket;

    while (true) {
        DeleteFile(commands.logFile.c_str());

        ClientSocket = accept(ListenSocket, NULL, NULL);
        if (ClientSocket == INVALID_SOCKET) {
            std::cerr << "accept failed with error: " << WSAGetLastError() << "Exit (1)" << std::endl;
            closesocket(ListenSocket);
            WSACleanup();
            return 1;
        }

        STARTUPINFO siPtd;
        PROCESS_INFORMATION piPtd;

        iResult = recv(ClientSocket, recvbuf, recvbuflen, 0);
        if (iResult > 0) {
            InitMessage *initMessage = (InitMessage *) recvbuf;
            std::cout << "Client command: " << initMessage->messageNumber << std::endl;
            bool is_ptd_started;

            char ptdCommand[commands.ptdStartCommand.length()];
            for (int i = 0; i < commands.ptdStartCommand.length(); i++) {
                ptdCommand[i] = commands.ptdStartCommand[i];
            }
            ptdCommand[commands.ptdStartCommand.length()] = '\0';

            is_ptd_started = executeSystemCommand(ptdCommand, &siPtd, &piPtd);
            if (!is_ptd_started) {
                char errMsg[] = "Can not start PTD";
                sentAnswer(ClientSocket, 1, errMsg);
            }
            ptdClientSocket = startPtdClient();

            if (ptdClientSocket < 0) {
                char errMsg[] = "Can not open client socket for PTD";
                sentAnswer(ClientSocket, 1, errMsg);
            }
            if (initMessage->messageNumber == 100) {
                sentMessage(ptdClientSocket, ptdSetAmps, strlen(ptdSetAmps));
                std::cout << "Message to PTD: " << ptdSetAmps << std::endl;
                recvPtdAnswer(ptdClientSocket);

                sentMessage(ptdClientSocket, ptdSetVolts, strlen(ptdSetVolts));
                std::cout << "Message to PTD: " << ptdSetVolts << std::endl;
                recvPtdAnswer(ptdClientSocket);

                sentMessage(ptdClientSocket, ptdGo, strlen(ptdGo));
                std::cout << "Message to PTD: " << ptdGo << std::endl;
                recvPtdAnswer(ptdClientSocket);
            } else {
                char buffer[DEFAULT_BUFLEN];
                sprintf(buffer, "SR,A,%f\r\n", initMessage->maxValues.maxAmps);
                std::cout << "Message to PTD: " << buffer << std::endl;
                sentMessage(ptdClientSocket, buffer, strlen(buffer));
                recvPtdAnswer(ptdClientSocket);

                memset(buffer, 0, DEFAULT_BUFLEN);
                sprintf(buffer, "SR,V,%f\r\n", initMessage->maxValues.maxVolts);
                std::cout << "Message to PTD: " << buffer << std::endl;
                sentMessage(ptdClientSocket, buffer, strlen(buffer));
                recvPtdAnswer(ptdClientSocket);

                sentMessage(ptdClientSocket, ptdGo, strlen(ptdGo));
                recvPtdAnswer(ptdClientSocket);
            }

            if (is_ptd_started && (ptdClientSocket > -1)) {
                char startMsg[] = "Start all needed processes";
                sentAnswer(ClientSocket, 0, startMsg);
            }
        }

        iResult = recv(ClientSocket, recvbuf, recvbuflen, 0);
        if (iResult > 0) {
            recvbuf[iResult] = '\0';

            std::cout << "Client command: " << recvbuf << std::endl;
            sentMessage(ptdClientSocket, ptdStop, strlen(ptdStop));
            closesocket(ptdClientSocket);
            WSACleanup();

            bool IsPtdDeamonClosed;
            IsPtdDeamonClosed = closeSystemProcess(&piPtd);
            if (!IsPtdDeamonClosed) {
                char errMsg[] = "Can not stop process daemon";
                sentAnswer(ClientSocket, 1, errMsg);
            } else {
                char errMsg[] = "Stop ptd.daemon";
                sentAnswer(ClientSocket, 0, errMsg);
            }
        }

        iResult = recv(ClientSocket, recvbuf, recvbuflen, 0);
        if (iResult > 0) {
            recvbuf[iResult] = '\0';
            std::cout << "Client command: " << recvbuf << std::endl;
            SendFile(ClientSocket, commands.logFile);
        }
    }

    iResult = shutdown(ClientSocket, SD_SEND);
    if (iResult == SOCKET_ERROR) {
        std::cerr << "shutdown failed with error: " << WSAGetLastError() << "Exit (1)" << std::endl;
        closesocket(ClientSocket);
        WSACleanup();
        return 1;
    }

    // cleanup
    closesocket(ClientSocket);
    WSACleanup();

    return 0;
}