#include "serverConfigParser.h"

std::string PORT = "port";
std::string QUIET_MODE = "quietMode";
std::string INCREASE_GENERAL_DEBUG_OUTPUT = "increaseGeneralDebugOutput";
std::string INCREASE_METER_SPECIFIC_DEBUG_OUTPUT = "increaseMeterSpecificDebugOutput";
std::string OPTION_LOGFILE = "logfile";
std::string EXTENDED_LOG_FILE_FORMAT = "extendedLogFileFormat";
std::string DEBUG_OUTPUT_TO_FILE = "debugOutputToFile";
std::string TEMPERATURE_MODE = "temperatureMode";
std::string VOLTAGE_AUTO_RANGE = "voltageAutoRange";
std::string AMPERE_AUTO_RANGE = "ampereAutoRange";
std::string BAUD_RATE = "baudRate";
std::string ENABLE_DC_MEASUREMENTS = "enableDcMeasurements";
std::string CHANNEL_NUMBER = "channelNumber";
std::string GPIB_INTERFACE = "GpibInterface";
std::string GPIB_BOARD_NUMBER = "GpibBoardNumber";
std::string USE_YOKOGAWA_USB_OR_ETHERNET_INTERFACE = "useYokogawaUsbOrEthernetInterface";

std::map<std::string, std::string> ptdKeys = {
        {PORT,                                   "-p"},
        {QUIET_MODE,                             "-q"},
        {INCREASE_GENERAL_DEBUG_OUTPUT,          "-v"},
        {INCREASE_METER_SPECIFIC_DEBUG_OUTPUT,   "-m"},
        {OPTION_LOGFILE,                         "-l"},
        {EXTENDED_LOG_FILE_FORMAT,               "-e"},
        {DEBUG_OUTPUT_TO_FILE,                   "-d"},
        {TEMPERATURE_MODE,                       "-t"},
        {VOLTAGE_AUTO_RANGE,                     "-V"},
        {BAUD_RATE,                              "-B"},
        {AMPERE_AUTO_RANGE,                      "-A"},
        {ENABLE_DC_MEASUREMENTS,                 "-D"},
        {CHANNEL_NUMBER,                         "-c"},
        {GPIB_INTERFACE,                         "-g"},
        {GPIB_BOARD_NUMBER,                      "-b"},
        {USE_YOKOGAWA_USB_OR_ETHERNET_INTERFACE, "-y"}};

bool isLogFileFlag(const char *elementName) {
    return (strcmp(elementName, OPTION_LOGFILE.c_str()) == 0);
}


void displayFlagParsingError(std::string elementNameString) {
    std::cerr << "Wrong JSON value for " << elementNameString << std::endl;
}

void displayEmptyLogFileParsingError() {
    std::cerr << "LogFile should not be empty " << std::endl;
}

bool isBoolValue(json_value_s *value) {
    return (json_value_is_true(value) || json_value_is_false(value));
}

void addKey(std::string *flagsString, const char *elementName) {
    (*flagsString) += " " + ptdKeys[elementName];
}

void addKeyWithValue(std::string *flagsString, const char *elementName, const char *elementValue) {
    (*flagsString) += " " + ptdKeys[elementName] + " " + elementValue;
}

void addLogFileValueToString(json_object_element_s *element, std::string *logFileString) {
    const char *elementName = element->name->string;
    if (isLogFileFlag(elementName)) {
        struct json_string_s *string = json_value_as_string(element->value);
        if (string == nullptr) {
            displayFlagParsingError(elementName);
        }

        if (string->string_size > 0) {
            copyStringValueToDataField(element->value, logFileString);
        } else {
            displayEmptyLogFileParsingError();
        }
    }
}

bool isBooleanFlag(const char *elementName) {
    return (strcmp(elementName, QUIET_MODE.c_str()) == 0 ||
            strcmp(elementName, INCREASE_GENERAL_DEBUG_OUTPUT.c_str()) == 0 ||
            strcmp(elementName, INCREASE_METER_SPECIFIC_DEBUG_OUTPUT.c_str()) == 0 ||
            strcmp(elementName, EXTENDED_LOG_FILE_FORMAT.c_str()) == 0 ||
            strcmp(elementName, TEMPERATURE_MODE.c_str()) == 0 ||
            strcmp(elementName, ENABLE_DC_MEASUREMENTS.c_str()) == 0 ||
            strcmp(elementName, GPIB_INTERFACE.c_str()) == 0);
}

bool isStringFlag(const char *elementName) {
    return (strcmp(elementName, OPTION_LOGFILE.c_str()) == 0 ||
            strcmp(elementName, DEBUG_OUTPUT_TO_FILE.c_str()) == 0 ||
            strcmp(elementName, VOLTAGE_AUTO_RANGE.c_str()) == 0 ||
            strcmp(elementName, AMPERE_AUTO_RANGE.c_str()) == 0 ||
            strcmp(elementName, USE_YOKOGAWA_USB_OR_ETHERNET_INTERFACE.c_str()) == 0);
}

bool isNumberFlag(const char *elementName) {
    return (strcmp(elementName, BAUD_RATE.c_str()) == 0 ||
            strcmp(elementName, CHANNEL_NUMBER.c_str()) == 0 ||
            strcmp(elementName, PORT.c_str()) == 0 ||
            strcmp(elementName, GPIB_BOARD_NUMBER.c_str()) == 0);
}

int addKeyIfElementIsBooleanFlag(json_object_element_s *element, std::string *flagsString) {
    const char *elementName = element->name->string;
    json_value_s *elementValue = element->value;
    if (isBooleanFlag(elementName)) {
        if (!isBoolValue(elementValue)) {
            displayFlagParsingError(elementName);
            return 1;
        }
        if (json_value_is_true(elementValue)) {
            addKey(flagsString, elementName);
            return 1;
        }
    }
    return 0;
}

int addKeyIfElementIsStringFlag(json_object_element_s *element, std::string *flagsString) {
    const char *elementName = element->name->string;
    json_value_s *elementValue = element->value;
    if (isStringFlag(elementName)) {
        struct json_string_s *string = json_value_as_string(elementValue);
        if (string == nullptr) {
            displayFlagParsingError(elementName);
            return 1;
        }

        const char *elementValue = string->string;
        if (strlen(elementValue) > 0) {
            addKeyWithValue(flagsString, elementName, elementValue);
        }

        return 1;
    }
    return 0;
}

int addKeyIfElementIsNumberFlag(json_object_element_s *element, std::string *flagsString) {
    const char *elementName = element->name->string;
    json_value_s *elementValue = element->value;
    if (isNumberFlag(elementName)) {
        struct json_number_s *number = json_value_as_number(elementValue);
        if (number == nullptr) {
            if (json_value_is_false(elementValue)) {
                return 1;
            }
            displayFlagParsingError(elementName);
            return 1;
        }

        const char *elementValue = number->number;
        if (strlen(elementValue) > 0) {
            addKeyWithValue(flagsString, elementName, elementValue);
        }
        return 1;
    }
    return 0;
}

void addFlagToString(json_object_element_s *element, std::string *ptdOptions) {
    if (addKeyIfElementIsBooleanFlag(element, ptdOptions)) {
        return;
    }
    if (addKeyIfElementIsNumberFlag(element, ptdOptions)) {
        return;
    }
    if (addKeyIfElementIsStringFlag(element, ptdOptions)) {
        return;
    }
}

void parseSeverCommands(json_object_element_s *element, void *data) {
    _ServerCommands *commands = (_ServerCommands *) data;
    const char *elementName = element->name->string;
    json_value_s *elementValue = element->value;
    if (strcmp(elementName, START_NTP_COMMAND) == 0) {
        copyStringValueToDataField(elementValue, &commands->ntp);
    } else if (strcmp(elementName, PTD_PATH) == 0) {
        copyStringValueToDataField(elementValue, &commands->ptdPath);
    } else if (strcmp(elementName, SERIAL_NUMBER) == 0) {
        copyStringValueToDataField(elementValue, &commands->serialNumber);
    } else if (strcmp(elementName, PTD_FLAGS) == 0) {
        struct json_object_element_s *flagElement = getStartElement(elementValue);
        while (flagElement != nullptr) {
            addFlagToString(flagElement, &commands->ptdOptions);
            addLogFileValueToString(flagElement, &commands->logFile);
            flagElement = flagElement->next;
        }
    } else {
        std::cout << "Wrong JSON key: " << element->name->string << std::endl;
        exit(0);
    }
}

ServerCommands getServerCommands(std::string fileName) {
    _ServerCommands data;
    ServerCommands commands;
    getCommands(&data, parseSeverCommands, fileName);
    commands.logFile += data.logFile;
    commands.ntp += data.ntp;
    commands.ptdStartCommand += data.ptdPath + " " + data.ptdOptions + " " + data.serialNumber;
    return commands;
}
