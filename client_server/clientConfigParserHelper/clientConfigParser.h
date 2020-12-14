//
// Created by julia on 25/11/2020.
//

#ifndef POWER_CLIENTCONFIGPARSER_H
#define POWER_CLIENTCONFIGPARSER_H
#include "clientServerParserLib.h"
#include <map>

constexpr auto RUN_NTP_COMMANDS = "ntpStartCommand";
constexpr auto RUN_TEST_COMMAND = "testCommands";
constexpr auto LOG_FILE = "logFile";
constexpr auto BUILD_FOLDER = "buildFolder";

struct ClientConfig {
    std::vector<std::string> ntp;
    std::map<std::string, std::string> testCommands;
    std::string logFile;
    std::string buildFolderPath;
};

ClientConfig getClientConfig(std::string fileName);
#endif //POWER_CLIENTCONFIGPARSER_H
