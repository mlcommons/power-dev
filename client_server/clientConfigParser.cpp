#include "clientConfigParser.h"

void parseClientCommands(json_object_element_s *element, void *data) {
    ClientConfig *commands = (ClientConfig *) data;
    json_value_s *elementValue = element->value;
    const char *elementNameString = element->name->string;
    if (strcmp(elementNameString, RUN_NTP_COMMANDS) == 0) {
        checkCommandValueExistence(commands->ntp);
        copyStringArrayToDataField(elementValue, &(commands->ntp));
    } else if (strcmp(elementNameString, RUN_TEST_COMMAND) == 0) {
        checkCommandValueExistence(commands->cli);
        copyStringArrayToDataField(elementValue, &commands->cli);
    } else if (strcmp(elementNameString, RUN_PARSER_COMMANDS) == 0) {
        checkCommandValueExistence(commands->parser);
        copyStringArrayToDataField(elementValue, &commands->parser);
    } else if (strcmp(elementNameString, MAX_AMPS_VOLTS_FILE) == 0) {
        copyStringValueToDataField(elementValue, &commands->maxAmpsVoltsFile);
    } else if (strcmp(elementNameString, CORRECTION_FACTOR) == 0) {
        copyFloatValueFromNumber(elementValue, &commands->correctionFactor);
    } else if (strcmp(elementNameString, LOG_FILE) == 0) {
        copyStringValueToDataField(elementValue, &commands->logFile);
    } else {
        std::cout << "Wrong JSON key" << std::endl;
        exit(0);
    }
}

ClientConfig getClientConfig(std::string fileName) {
    ClientConfig data;
    getCommands(&data, parseClientCommands, fileName);
    return data;
}


