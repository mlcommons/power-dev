//
// Created by julia on 01/12/2020.
//

#include "maxAmpsVoltsParser.h"

void parseMaxAmpsVolts(json_object_element_s* element, void * data) {
    MaxAmpsVolts * maxAmpsVoltsValues = (MaxAmpsVolts *) data;
    json_value_s * elementValue = element->value;
    const char * elementNameString = element->name->string;
    if (strcmp(elementNameString, MAX_AMPS) == 0) {
        copyFloatValueFromString(elementValue, &maxAmpsVoltsValues->maxAmps);
    } else if (strcmp(elementNameString, MAX_VOLTS) == 0) {
        copyFloatValueFromString(elementValue, &maxAmpsVoltsValues->maxVolts);
    } else {
        std::cout << "Wrong JSON key" << std::endl;
        exit(0);
    }
}

MaxAmpsVolts getMaxAmpsVolts(std::string fileName) {
    MaxAmpsVolts data;
    getCommands(&data, parseMaxAmpsVolts, fileName);
    return data;
}
