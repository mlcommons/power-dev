
#ifndef POWER_CLIENTSERVERPARSERLIB_H
#define POWER_CLIENTSERVERPARSERLIB_H
#include "./../json.h/json.h"
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

void copyCommandWithCheck(struct json_string_s*, std::vector<std::string>*);
void copyStringFromArrayToData(struct json_array_element_s*, std::vector<std::string>*);
void copyStringArrayToDataField(struct json_value_s*, std::vector<std::string>* );
void checkCommandValueExistence(std::vector<std::string>);
std::string getLineFromFile(std::string);
struct json_object_element_s* getStartElementFromFile(std::string, struct json_value_s*);
void copyStringValueToDataField(struct json_value_s*, std::string *);
struct json_object_element_s* getStartElement(struct json_value_s*);
void getCommands(void *, void(* parseClientCommands)(json_object_element_s*, void *), std::string);
void copyFloatValueFromString(struct json_value_s* , float *);
void copyFloatValueFromNumber(struct json_value_s *, float *);
#endif //POWER_CLIENT_H