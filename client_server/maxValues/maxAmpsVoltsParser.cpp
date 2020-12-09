//
// Created by julia on 01/12/2020.
//

#include "maxAmpsVoltsParser.h"

void parseMaxAmpsVolts(json_object_element_s* element, void * data) {
    std::map <std::string, MaxAmpsVolts> * testResults = (std::map <std::string, MaxAmpsVolts> *) data;
    MaxAmpsVolts maxValues;
    const char * testName = element->name->string;
    json_value_s * testValue = element->value;
    struct json_object_s* object = json_value_as_object(testValue);

    //TODO:Add check
    struct json_object_element_s* maxValuesElement = object->start;

    while (maxValuesElement != nullptr) {
        const char *elementNameString = maxValuesElement->name->string;
        json_value_s * elementValue = maxValuesElement->value;
        if (strcmp(elementNameString, MAX_AMPS) == 0) {
            copyFloatValueFromString(elementValue, &maxValues.maxAmps);
        } else if (strcmp(elementNameString, MAX_VOLTS) == 0) {
            copyFloatValueFromString(elementValue, &maxValues.maxVolts);
        } else {
            std::cout << "Wrong JSON key" << std::endl;
            exit(0);
        }
        maxValuesElement = maxValuesElement->next;
    }
    (* testResults)[std::string(testName)] = maxValues;
}

std::map <std::string, MaxAmpsVolts> getMaxAmpsVolts(std::string fileName) {
    std::map <std::string, MaxAmpsVolts> data;
    getCommands(&data, parseMaxAmpsVolts, fileName);
    std::map <std::string, MaxAmpsVolts> :: iterator it = data.begin();

    for (; it != data.end(); it++) {
        std::cout << it->first << " " << it->second.maxAmps << " " << it->second.maxVolts << std::endl;
    }
    return data;
}