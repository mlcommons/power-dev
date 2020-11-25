//
// Created by julia on 25/11/2020.
//

#ifndef POWER_CLIENTCONFIGPARSER_H
#define POWER_CLIENTCONFIGPARSER_H
#include "clientServerParserLib.h"

#define RUN_NTP_COMMANDS "ntpStartCommand"
#define RUN_TEST_COMMAND "testCommands"
#define RUN_PARSER_COMMANDS "parserCommand"

struct Commands {
    std::vector<std::string> ntp;
    std::vector<std::string> cli;
    std::vector<std::string> parser;
};

Commands getClientCommands(std::string fileName);
#endif //POWER_CLIENTCONFIGPARSER_H
