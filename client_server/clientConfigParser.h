//
// Created by julia on 25/11/2020.
//

#ifndef POWER_CLIENTCONFIGPARSER_H
#define POWER_CLIENTCONFIGPARSER_H
#include "clientServerParserLib.h"

constexpr auto RUN_NTP_COMMANDS = "ntpStartCommand";
constexpr auto RUN_TEST_COMMAND = "testCommands";
constexpr auto RUN_PARSER_COMMANDS = "parserCommand";
constexpr auto MAX_AMPS_VOLTS_FILE = "maxAmpsVoltsFilePath";
constexpr auto CORRECTION_FACTOR = "correctionFactor";
constexpr auto LOG_FILE = "logFile";

struct ClientConfig {
    std::vector<std::string> ntp;
    std::vector<std::string> cli;
    std::vector<std::string> parser;
    std::string maxAmpsVoltsFile;
    std::string logFile;
    float correctionFactor;
};

ClientConfig getClientConfig(std::string fileName);
#endif //POWER_CLIENTCONFIGPARSER_H
