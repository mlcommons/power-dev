//
// Created by julia on 01/12/2020.
//

#ifndef POWER_MAXAMPSVOLTSPARSER_H
#define POWER_MAXAMPSVOLTSPARSER_H
#include "./../clientServerParserLib/clientServerParserLib.h"
#include <map>

constexpr auto MAX_AMPS = "maxAmps";
constexpr auto MAX_VOLTS = "maxVolts";

struct MaxAmpsVolts {
    float maxAmps;
    float maxVolts;
};

std::map <std::string, MaxAmpsVolts> getMaxAmpsVolts(std::string fileName);
#endif //POWER_MAXAMPSVOLTSPARSER_H
