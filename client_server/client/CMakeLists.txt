cmake_minimum_required(VERSION 3.10)
project(Client_Server VERSION 1.0)

project(Client_Server)

set(SUBDIRS ./../clientConfigParserHelper ./../clientServerParserLib ./../maxValues ./../interacting_with_process)

include_directories(./../cxxopts ./../json.h ${SUBDIRS})

add_executable(client client.cpp ./../maxValues/maxAmpsVoltsParser.cpp ./../clientServerParserLib/clientServerParserLib.cpp
        ./../clientConfigParserHelper/clientConfigParser.cpp ./../interacting_with_process/interacting_with_process.cpp)
