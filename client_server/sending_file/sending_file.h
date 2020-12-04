#ifndef POWER_SENDING_FILE_H
#define POWER_SENDING_FILE_H

#include <iostream>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <fstream>

int64_t SendFile(SOCKET, const std::string &fileName, int chunkSize = DEFAULT_FILE_CHUNK_SIZE);
#endif //POWER_SENDING_FILE_H
