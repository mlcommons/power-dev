cmake_minimum_required(VERSION 3.10)
project(Client_Server VERSION 1.0)

project(Client_Server)

set(SUBDIRS ../clientServerParserHelper ../clientServerParserHelper)
set(CMAKE_CXX_FLAGS "-mwin32")

include_directories(./../cxxopts ./../json.h ${SUBDIRS})

add_executable(server server.cpp ../clientServerParserLib/clientServerParserLib.cpp ./../serverConfigParserHelper/serverConfigParser.cpp)

target_link_libraries(server ws2_32)