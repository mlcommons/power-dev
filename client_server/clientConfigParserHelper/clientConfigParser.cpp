#include "clientConfigParser.h"

void parseTestCommands(json_value_s* testCommandsValue, std::map <std::string, std::string> * testCommands) {
    struct json_object_s* object = json_value_as_object(testCommandsValue);
    if (object == nullptr) {
        std::cerr << "Value of object 'test commands' should be an JSON object" << std::endl;
        exit(1);
    }
    struct json_object_element_s* element = object->start;

    for (int i = 0; i < object->length; i++) {
        struct json_array_s* array = json_value_as_array(element->value);
        if (array->length == 0) {
            (*testCommands)["W" + std::to_string(i+1) + "S" + std::to_string(1)] = std::string(element->name->string);
            element = element->next;
            continue;
        }

        struct json_array_element_s* setting = array->start;
        if (setting != nullptr) {
            for (int j = 0; j < array->length; j++) {
                struct json_string_s* settingString = json_value_as_string(setting->value);
                if (settingString != nullptr) {
                    (*testCommands)["W" + std::to_string(i + 1) + "S" + std::to_string(j + 1)] = std::string(element->name->string) + " " + std::string(settingString->string);
                }
                setting->next;
            }
        }
        element = element->next;
    }
}

void parseClientCommands(json_object_element_s *element, void *data) {
    ClientConfig *commands = (ClientConfig *) data;
    json_value_s *elementValue = element->value;
    const char *elementNameString = element->name->string;
    if (strcmp(elementNameString, RUN_NTP_COMMANDS) == 0) {
        checkCommandValueExistence(commands->ntp);
        copyStringArrayToDataField(elementValue, &(commands->ntp));
    } else if (strcmp(elementNameString, RUN_TEST_COMMAND) == 0) {
        parseTestCommands(elementValue, &commands->testCommands);
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
        std::cerr << "Wrong JSON key" << std::endl;
        exit(0);
    }
}

ClientConfig getClientConfig(std::string fileName) {
    ClientConfig data;
    getCommands(&data, parseClientCommands, fileName);
    return data;
}
