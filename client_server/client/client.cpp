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


#include "./client.h"

int receiveBuffer(int s, char *buffer, int bufferSize, int chunkSize = DEFAULT_BUFFER_CHUNK_SIZE) {
    int allReceivedBytes = 0;
    while (allReceivedBytes < bufferSize) {
        const int currentReceivedBytes = recv(s, &buffer[allReceivedBytes],
                                              std::min(chunkSize, bufferSize - allReceivedBytes), 0);
        if (currentReceivedBytes < 0) {
            return currentReceivedBytes;
        }
        allReceivedBytes += currentReceivedBytes;
    }
    return allReceivedBytes;
}

int64_t receiveFile(int sock, const std::string &fileName, int chunkSize = DEFAULT_FILE_CHUNK_SIZE) {
    std::ofstream file(fileName, std::ofstream::binary);
    if (file.fail()) {
        std::cerr << "Can not create ofstream" << std::endl << "Exit (1)" << std::endl;
        exit(1);
    }

    int64_t fileSize;
    //Get file size
    if (recv(sock, (char *) (&fileSize), sizeof(fileSize), 0) != sizeof(fileSize)) {
        std::cerr << "Can not get file size" << std::endl << "Exit (1)" << std::endl;
        exit(1);
    }
    //Get file
    char *buffer = new char[chunkSize];
    bool errored = false;
    int64_t bytesForReading = fileSize;
    while (bytesForReading != 0) {
        const int receivedBytes = receiveBuffer(sock, buffer, (int) std::min(bytesForReading, (int64_t) chunkSize));
        if ((receivedBytes < 0) || !file.write(buffer, receivedBytes)) {
            errored = true;
            break;
        }
        bytesForReading -= receivedBytes;
    }
    delete[] buffer;

    file.close();

    if (errored == true) {
        std::cerr << "Can not write file " << fileName << std::endl << "Exit (1)" << std::endl;
        exit(1);
    }

    return fileSize;
}

void receiveServerAnswer(int sock) {
    int buf_len = sizeof(ServerAnswer);
    char buffer[buf_len] = {0};
    int readBytesNum = recv(sock, buffer, buf_len, 0);
    if (readBytesNum < 0) {
        std::cerr << "Error reading server message: " << strerror(errno) << std::endl;
        exit(1);
    }
    ServerAnswer *answer = (ServerAnswer *) buffer;

    std::cerr << "Server send a message: " << answer->message << std::endl;

    if (answer->code != 0) {
        exit(1);
    }
}

void sendCommandToServer(int sock, const char *msg) {
    char message[DEFAULT_BUFLEN];
    strcpy(message, msg);
    send(sock, message, strlen(message), 0);
    std::cout << "Send command to server: " << message << std::endl;
}

void sendMsg(int sock, std::string fileName) {
    SaveLogMessage message;
    message.code = RUN;
    sprintf(message.fileName, fileName.c_str());

    send(sock, (char *) &message, sizeof(SaveLogMessage), 0);

    std::cout << "Send command to server: " << message.fileName << std::endl;
}

void executeCommand(std::string command) {
    std::cerr << command << std::endl;
    int returnCode = system(command.c_str());
    if (returnCode != 0) {
        std::cerr << "Could not execute " << command << std::endl;
    }
}

void executeCommands(std::vector<std::string> commands){
    for (int i = 0; i < commands.size(); i++) {
        executeCommand(commands[i]);
    }
}

int main(int argc, char const *argv[]) {
    std::string serverIpAddress;
    std::string configurationFile;
    int serverPort;
    bool isRangingMode = false;

    cxxopts::Options options("PTD client", "A brief description");

    options.add_options()
            ("p,serverPort", "Server port", cxxopts::value<int>()->default_value("4950"))
            ("i,serverIpAddress", "Server ip address", cxxopts::value<std::string>())
            ("c,configurationFile", "Client configuration file path",
             cxxopts::value<std::string>()->default_value("config.txt"))
            ("r,ranging", "Ranging mode", cxxopts::value<bool>()->default_value("false"))
            ("h,help", "Print usage");

    auto result = options.parse(argc, argv);

    if (result.count("help")) {
        std::cout << options.help() << std::endl;
        exit(0);
    }

    if (result.count("ranging")) {
        isRangingMode = true;
    }

    if (result.count("serverIpAddress")) {
        serverIpAddress = result["serverIpAddress"].as<std::string>();
    } else {
        std::cout << "Server ip address is required" << std::endl;
        return 1;
    }

    serverPort = result["serverPort"].as<int>();
    configurationFile = result["configurationFile"].as<std::string>();

    ClientConfig data = getClientConfig(configurationFile);
    executeCommands(data.ntp);

    int sock = 0;
    struct sockaddr_in ServerAddress;
    if ((sock = socket(AF_INET, SOCK_STREAM, 0)) < 0) {
        std::cerr << "Socket creation error " << std::endl;
        return 1;
    }

    ServerAddress.sin_family = AF_INET;
    ServerAddress.sin_port = htons(serverPort);

    if (inet_pton(AF_INET, serverIpAddress.c_str(), &ServerAddress.sin_addr) <= 0) {
        std::cerr << "Invalid address/ Address not supported " << std::endl;
        return 1;
    }

    if (connect(sock, (struct sockaddr *) &ServerAddress, sizeof(ServerAddress)) < 0) {
        std::cerr << "Connection Failed " << std::endl << "Exit (1)" << std::endl;
    }

    std::map<std::string, std::string>::iterator itr;

    sendCommandToServer(sock, START_RANGING);

    for (itr = data.testCommands.begin(); itr != data.testCommands.end(); ++itr) {
        sendCommandToServer(sock, RUN_STR);
        receiveServerAnswer(sock);

        executeCommand(itr->second);

        sendCommandToServer(sock, STOP);
        receiveServerAnswer(sock);

        sendCommandToServer(sock, itr->first.c_str());
        receiveServerAnswer(sock);

        sleep(5);
     }

    sendCommandToServer(sock, START_TESTING);

    sendCommandToServer(sock, START_TESTING);
    receiveServerAnswer(sock);

    for (itr = data.testCommands.begin(); itr != data.testCommands.end(); ++itr) {
        std::cout << sizeof(SaveLogMessage) << std::endl;
        sendMsg(sock, itr->first.c_str());
        receiveServerAnswer(sock);

        executeCommand(itr->second);

        sendCommandToServer(sock, STOP);
        receiveServerAnswer(sock);

        sendCommandToServer(sock, GET_FILE);
        receiveFile(sock, itr->first.c_str());

        sleep(5);
    }


//    sendCommandToServer(sock, GET_FILE);
//    receiveFile(sock, data.logFile);


    return 0;
}
