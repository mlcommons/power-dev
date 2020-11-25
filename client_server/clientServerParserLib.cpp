#include "json.h/json.h"
#include "clientServerParserLib.h"

void copyCommandWithCheck(struct json_string_s* command, std::vector<std::string> * commands){
    if (command != NULL) {
        (*commands).push_back(command->string);
    } else {
        std::cout << "Wrong JSON value" << std::endl;
        exit(1);
    }
}

void copyStringFromArrayToData(struct json_array_element_s* element, std::vector<std::string> * commands) {
    struct json_string_s* command = json_value_as_string(element->value);
    copyCommandWithCheck(command, commands);
}

void copyStringArrayToDataField(struct json_value_s* element, std::vector<std::string> *commands) {
    struct json_array_s* array = json_value_as_array(element);
    if (array != NULL) {
        struct json_array_element_s* command = array->start;
        copyStringFromArrayToData(command, commands);
        while (command->next != NULL) {
            command = command->next;
            copyStringFromArrayToData(command, commands);
        }
    } else {
        struct json_string_s* command = json_value_as_string(element);
        copyCommandWithCheck(command, commands);
    }
}

void checkCommandBlockExistance(std::vector<std::string> * commands){
    if((*commands).size() != 0) {
        std::cout << "Wrong JSON object, there are the same keys" << std::endl;
        exit(1);
    }
}

std::string getLineFromFile(std::string fileName) {
    std::ifstream input_file(fileName, std::ifstream::in);
    std::string dna;
    std::string text_read;
    while (std::getline(input_file, text_read))
    {
        const std::string::size_type position = text_read.find(END_OF_LINE);
        if (position != std::string::npos)
        {
            text_read.erase(position);
        }
        dna += text_read;
    }
    return dna;
}

struct json_object_element_s* getStartElement(std::string jsonString, struct json_value_s* root) {
    char json[jsonString.length() + 1];
    strcpy(json, jsonString.c_str());

    root = json_parse(json, strlen(json));

    if (root == NULL) {
        std::cerr << "Wrong JSON string" << std::endl;
        exit(0);
    }

    struct json_object_s* object = json_value_as_object(root);

    if (object == NULL) {
        std::cerr << "Wrong JSON object" << std::endl;
        exit(0);
    }

    struct json_object_element_s* element = object->start;

    return element;
}