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

#include "server.h"

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
        iResult = connect(ConnectSocket, (SOCKADDR * ) & clientService, sizeof(clientService));
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

void getCharFromString(std::string str, char* charArray){
    for (int i = 0; i < str.length(); i++) {
        charArray[i] = str[i];
    }
    charArray[str.length()] = '\0';
}

int __cdecl main(int argc, char const *argv[]) {
    char ptdSetAmpsAuto[] = "SR,A,Auto\r\n";
    char ptdSetAmps[] = "SR,A,%f\r\n";
    char ptdStartRanging[] = "Go,1000,0,%s\r\n";
    char ptdSetVolts[] = "SR,V,300\r\n";
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
    getCharFromString(commands.ntp, ntpCommand);
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

    while (true) {
        ClientSocket = accept(ListenSocket, NULL, NULL);
        if (ClientSocket == INVALID_SOCKET) {
            std::cerr << "accept failed with error: " << WSAGetLastError() << "Exit (1)" << std::endl;
            closesocket(ClientSocket);
            WSACleanup();
            return 1;
        }

        iResult = recv(ClientSocket, recvbuf, recvbuflen, 0);
        if (iResult < 0) {
            //TODO: Add error msg
            continue;
        }

        StartTestMessage *msg = (StartTestMessage *) recvbuf;

        if (msg->code != START) {
            //TODO: Send err msg
            continue;
        };

        std::cout << commands.logFile << std::endl;
        DeleteFile(commands.logFile.c_str());

        STARTUPINFO siPtd;
        PROCESS_INFORMATION piPtd;

        char ptdCommand[commands.ptdStartCommand.length()];
        getCharFromString(commands.ptdStartCommand, ptdCommand);

        bool is_ptd_started = executeSystemCommand(ptdCommand, &siPtd, &piPtd);
        if (!is_ptd_started) {
            char errMsg[] = "Can not start PTD";
            exit(0);
        }

        int ptdClientSocket = startPtdClient();
        if (ptdClientSocket < 0) {
            char errMsg[] = "Can not open client socket for PTD";
            sentAnswer(ClientSocket, 1, errMsg);
            exit(0);
        }

        if (is_ptd_started && (ptdClientSocket > -1)) {
            char startMsg[] = "Start all needed processes";
            sentAnswer(ClientSocket, 0, startMsg);
        }

        std::map <std::string, MaxAmpsVolts> maxAmpsVolts;
        std::string prevCommand = "";

        int workloadAmount = msg->workloadAmount;

        for (int i = 0; i < MODE_AMOUNT; i++) {
            std::cout << "Start " << (i == MODE_RANGING ? "ranging " : "testing ") << " mode" << std::endl;
            for (int j = 0; j < workloadAmount; j++) {

                iResult = recv(ClientSocket, recvbuf, recvbuflen, 0);
                if (iResult > 0) {
                    recvbuf[iResult] = '\0';
                    StartLogMessage *startMsg = (StartLogMessage *) recvbuf;
                    if (startMsg->code == START_LOG) {
                        if (i == MODE_RANGING && prevCommand != std::string(ptdSetAmpsAuto)) {
                            prevCommand = std::string(ptdSetAmpsAuto);
                            sentMessage(ptdClientSocket, ptdSetAmpsAuto, strlen(ptdSetAmpsAuto));
                            recvPtdAnswer(ptdClientSocket);
                            std::cout << "Message to PTD: " << ptdSetAmpsAuto << std::endl;
                            sentMessage(ptdClientSocket, ptdSetVolts, strlen(ptdSetVolts));
                            recvPtdAnswer(ptdClientSocket);
                            std::cout << "Message to PTD: " << ptdSetVolts << std::endl;
                            Sleep(SLEEP_PTD_AFTER_CHANGING_RANGE);
                        }
                        if (i == MODE_TESTING) {
                            char buffer[DEFAULT_BUFLEN];
                            sprintf(buffer, ptdSetAmps, maxAmpsVolts[std::string(startMsg->workloadName)].maxAmps);
                            if (prevCommand != std::string(buffer)) {
                                prevCommand = std::string(buffer);
                                sentMessage(ptdClientSocket, buffer, strlen(buffer));
                                recvPtdAnswer(ptdClientSocket);
                                std::cout << "Message to PTD: " << buffer << std::endl;
                                Sleep(SLEEP_PTD_AFTER_CHANGING_RANGE);
                            }
                        }

                        char buffer[DEFAULT_BUFLEN];
                        sprintf(buffer, ptdStartRanging, startMsg->workloadName);
                        sentMessage(ptdClientSocket, buffer, strlen(buffer));
                        std::cout << "Message to PTD: " << buffer << std::endl;
                        recvPtdAnswer(ptdClientSocket);
                        char msg[] = "Start writing logs";
                        sentAnswer(ClientSocket, 0, msg);
                    }
                }

                iResult = recv(ClientSocket, recvbuf, recvbuflen, 0);
                if (iResult > 0) {
                    recvbuf[iResult] = '\0';
                    if (atoi(recvbuf) == STOP_LOG) {
                        std::cout << "Client command: " << recvbuf << std::endl;
                        sentMessage(ptdClientSocket, ptdStop, strlen(ptdStop));
                        recvPtdAnswer(ptdClientSocket);
                        char msg[] = "Stop writing logs";
                        sentAnswer(ClientSocket, 0, msg);
                    }
                }
            }

            if (i == MODE_RANGING) {
                std::string script = std::string(MAX_AMPS_VOLTS_VALUE_SCRIPT) + " " + commands.logFile;

                STARTUPINFO siScript;
                PROCESS_INFORMATION piScript;

                char scriptCommand[script.length()];
                getCharFromString(script, scriptCommand);

                executeSystemCommand(scriptCommand, &siScript, &piScript);
                //TODO: Change INFINITE time?
                WaitForSingleObject(piScript.hProcess, INFINITE);

                CloseHandle(piScript.hProcess);
                CloseHandle(piScript.hThread);

                maxAmpsVolts = getMaxAmpsVolts(std::string(MAX_AMPS_VOLTS_VALUE_FILE));
            }
        }

        SendFile(ClientSocket, commands.logFile);

        closesocket(ptdClientSocket);
        WSACleanup();

        bool IsPtdDeamonClosed;
        IsPtdDeamonClosed = closeSystemProcess(&piPtd);

        if (!IsPtdDeamonClosed) {
            std::cout << "Couldn't close PTD " << std::endl;
        }
    }

    iResult = shutdown(ClientSocket, SD_SEND);
    if (iResult == SOCKET_ERROR) {
        std::cerr << "shutdown failed with error: " << WSAGetLastError() << "Exit (1)" << std::endl;
        closesocket(ClientSocket);
        WSACleanup();
        return 1;
    }

    closesocket(ClientSocket);
    WSACleanup();

    return 0;
}