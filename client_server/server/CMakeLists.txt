cmake_minimum_required(VERSION 3.10)
project(Client_Server VERSION 1.0)

project(Client_Server)

set(SUBDIRS ../clientServerParserHelper ../clientServerParserHelper ../interacting_with_process ../sending_file ./../maxValues)
set(CMAKE_CXX_FLAGS "-mwin32")

include_directories(./../cxxopts ./../json.h ${SUBDIRS})

add_executable(server server.cpp ../clientServerParserLib/clientServerParserLib.cpp ./../serverConfigParserHelper/serverConfigParser.cpp
        ./../interacting_with_process/interacting_with_process.cpp ./../sending_file/sending_file.cpp  ./../maxValues/maxAmpsVoltsParser.cpp)
set_target_properties(server PROPERTIES CXX_STANDARD 17)
target_link_libraries(server ws2_32)