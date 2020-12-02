#include "clientServerParserLib.h"

void copyCommandWithCheck(struct json_string_s *command, std::vector <std::string> *commands) {
    if (command != nullptr) {
        (*commands).push_back(command->string);
    } else {
        std::cerr << "Wrong JSON value" << std::endl;
        exit(1);
    }
}

void copyStringFromArrayToData(struct json_array_element_s *element, std::vector <std::string> *commands) {
    struct json_string_s *command = json_value_as_string(element->value);
    copyCommandWithCheck(command, commands);
}

void copyStringArrayToDataField(struct json_value_s *element, std::vector <std::string> *commands) {
    struct json_array_s *array = json_value_as_array(element);
    if (array != nullptr) {
        struct json_array_element_s *command = array->start;
        copyStringFromArrayToData(command, commands);
        while (command->next != nullptr) {
            command = command->next;
            copyStringFromArrayToData(command, commands);
        }
    } else {
        struct json_string_s *command = json_value_as_string(element);
        copyCommandWithCheck(command, commands);
    }
}

void copyStringValueToDataField(struct json_value_s *element, std::string *command) {
    if (element->type != json_type_string) {
        std::cerr << "Wrong config file" << std::endl;
    }

    struct json_string_s *string = json_value_as_string(element);
    (*command) += string->string;
}

void copyFloatValueFromString(struct json_value_s *element, float *value) {
    if (element->type != json_type_string) {
        std::cerr << "Wrong config file" << std::endl;
    }

    struct json_string_s *number = json_value_as_string(element);
    (*value) = std::stof(number->string);
}

void copyFloatValueFromNumber(struct json_value_s *element, float *value) {
    if (element->type != json_type_number) {
        std::cerr << "Wrong config file" << std::endl;
    }

    struct json_number_s *number = json_value_as_number(element);
    (*value) = std::stof(number->number);
}

void checkCommandValueExistence(std::vector <std::string> commands) {
    if (commands.size() != 0) {
        std::cerr << "Wrong JSON object, there are the same keys" << std::endl;
        exit(1);
    }
}

std::string getLineFromFile(std::string fileName) {
    std::ifstream input_file(fileName, std::ifstream::in);
    std::string dna;
    std::string text_read;
    while (std::getline(input_file, text_read)) {
        const std::string::size_type position = text_read.find(END_OF_LINE);
        if (position != std::string::npos) {
            text_read.erase(position);
        }
        dna += text_read;
    }
    return dna;
}

struct json_object_s *getJsonObject(struct json_value_s *root) {
    struct json_object_s *object = json_value_as_object(root);

    if (object == nullptr) {
        std::cerr << "Wrong JSON object" << std::endl;
        exit(0);
    }

    return object;
}

struct json_object_element_s *getStartElement(struct json_value_s *root) {
    struct json_object_s *object = getJsonObject(root);
    struct json_object_element_s *element = object->start;

    if (element == nullptr) {
        std::cerr << "Wrong json, empty element" << std::endl;
        exit(0);
    }

    return element;
}

struct json_object_element_s *getStartElementFromFile(std::string jsonString, struct json_value_s *root) {
    char json[jsonString.length() + 1];
    strcpy(json, jsonString.c_str());
    root = json_parse(json, strlen(json));

    if (root == nullptr) {
        std::cerr << "Wrong JSON string" << std::endl;
        exit(0);
    }

    struct json_object_s *object = getJsonObject(root);

    struct json_object_element_s *element = object->start;

    return element;
}

void getCommands(void *data, void (*parseClientCommands)(json_object_element_s *, void *), std::string fileName) {
    struct json_value_s *root = nullptr;
    struct json_object_element_s *element = getStartElementFromFile(getLineFromFile(fileName), root);

    while (element != nullptr) {
        parseClientCommands(element, data);
        element = element->next;
    }

    free(root);
}