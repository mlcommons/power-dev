#include "json.h/json.h"
#include "clientConfigParser.h"
#include "clientServerParserLib.h"

void getCommands(json_object_element_s* element, Commands * data) {
    struct json_string_s* element_name = element->name;
    if (strcmp(element_name->string, RUN_NTP_COMMANDS) == 0) {
        checkCommandBlockExistance(&data->ntp);
        copyStringArrayToDataField(element->value, &data->ntp);
    } else if (strcmp(element_name->string, RUN_TEST_COMMAND) == 0) {
        checkCommandBlockExistance(&data->cli);
        copyStringArrayToDataField(element->value, &data->cli);
    } else if (strcmp(element_name->string, RUN_PARSER_COMMANDS) == 0) {
        checkCommandBlockExistance(&data->parser);
        copyStringArrayToDataField(element->value, &data->parser);
    } else {
        std::cout << "Wrong JSON key" << std::endl;
        exit(0);
    }
}

Commands getClientCommands(std::string fileName) {
    Commands data;
    struct json_value_s* root = NULL;

    struct json_object_element_s* element = getStartElement(getLineFromFile(fileName), root);

    if (element == NULL) {
        std::cerr << "Empty json" << std::endl;
        exit(0);
    } else {
        getCommands(element, &data);
    }

    while (element->next != NULL) {
        element = element->next;
        getCommands(element, &data);
    }

    return data;
}
