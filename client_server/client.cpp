//Build command: g++ -o client client.cpp

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
#include "./cxxopts/include/cxxopts.hpp"

#define PYTHON_COMMAND "python3.8 parse_mlperf.py -pli logs.txt -lgi ./build"
#define NTPD_COMMAND "sudo /usr/sbin/ntpdate time.windows.com"

#define RUN "100"
#define STOP "200"
#define GET_FILE "500"

#define DEFAULT_BUFFER_CHUNK_SIZE 4096
#define DEFAULT_FILE_CHUNK_SIZE 65536
#define DEFAULT_BUFLEN 512

struct ServerAnswer {
    int code;
    char message[DEFAULT_BUFLEN];
};

struct InitMessage {
    int messageNumber;
    float averageFloat;
};

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

void sendInitialCommandToServer(int sock, bool isRangingMode) {
    InitMessage message;
    message.messageNumber = isRangingMode ? 100 : 101;
    //TODO add func to get average
    message.averageFloat = isRangingMode ? 0 : 2.1;
    send(sock, (char *) &message, sizeof(InitMessage), 0);
    std::cout << "Send command to server: " << message.messageNumber << std::endl;
}

int main(int argc, char const *argv[]) {
    std::string serverIpAddress;
    std::string configurationFile;
    std::string logFile;
    int serverPort;
    bool isRangingMode = false;

    cxxopts::Options options("PTD client", "A brief description");

    options.add_options()
            ("p,serverPort", "Server port", cxxopts::value<int>()->default_value("4950"))
            ("i,serverIpAddress", "Server ip address", cxxopts::value<std::string>())
            ("c,configurationFile", "Client configuration file path",
             cxxopts::value<std::string>()->default_value("config.txt"))
            ("l,ptdLogFilePath", "Path to save PTD logfile", cxxopts::value<std::string>()->default_value("logs.txt"))
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

    logFile = result["ptdLogFilePath"].as<std::string>();
    serverPort = result["serverPort"].as<int>();
    configurationFile = result["configurationFile"].as<std::string>();

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

    int ntpStartedCode = system(NTPD_COMMAND);
    if (ntpStartedCode != 0) {
        std::cerr << "Can not start NTPd" << std::endl;
    }

    sendInitialCommandToServer(sock, isRangingMode);
    receiveServerAnswer(sock);

    //TODO: move commands in config file
    system("sudo dd if=/dev/sda of=/tmp/tt.dd bs=1M count=3500");
    system("7zr a -t7z  -mx=9 -m0=LZMA2 -mmt8 /tmp/dd1.7z /tmp/tt.dd");

    sendCommandToServer(sock, STOP);
    receiveServerAnswer(sock);

    sendCommandToServer(sock, GET_FILE);
    receiveFile(sock, logFile);

    system(PYTHON_COMMAND);
    return 0;
}
