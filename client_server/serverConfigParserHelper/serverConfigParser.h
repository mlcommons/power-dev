//
// Created by julia on 26/11/2020.
//

#ifndef POWER_SERVERCONFIGPARSER_H
#define POWER_SERVERCONFIGPARSER_H
#include "clientServerParserLib.h"
#include <map>

#define START_NTP_COMMAND "ntpStartCommand"
#define PTD_PATH "ptdPath"
#define PTD_FLAGS "ptdFlags"
#define SERIAL_NUMBER "serialNumber"

struct _ServerCommands {
    std::string ntp;
    std::string ptdPath;
    std::string ptdOptions;
    std::string logFile;
    std::string serialNumber;
};

struct ServerCommands {
    std::string ntp;
    std::string ptdStartCommand;
    std::string logFile;
};
ServerCommands getServerCommands(std::string fileName);
#endif //POWER_SERVERCONFIGPARSER_H
