
#ifndef POWER_CLIENTSERVERPARSERLIB_H
#define POWER_CLIENTSERVERPARSERLIB_H
#include "json.h/json.h"
#include <stdio.h>
#include <string.h>
#include <iostream>
#include <vector>
#include <fstream>

#ifdef _WIN32
#define END_OF_LINE '\r'
#else
#define END_OF_LINE '\n'
#endif


void copyCommandWithCheck(struct json_string_s* command, std::vector<std::string> * commands);
void copyStringFromArrayToData(struct json_array_element_s* element, std::vector<std::string> * commands);
void copyStringArrayToDataField(struct json_value_s* element, std::vector<std::string> *commands);
void checkCommandBlockExistance(std::vector<std::string> * commands);
std::string getLineFromFile(std::string fileName);
struct json_object_element_s* getStartElement(std::string jsonString, struct json_value_s* root);

#endif //POWER_CLIENT_H