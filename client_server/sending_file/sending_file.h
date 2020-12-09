#ifndef POWER_SENDING_FILE_H
#define POWER_SENDING_FILE_H

#include <winsock2.h>
#include <stdlib.h>
#include <iostream>
#include <fstream>

#define DEFAULT_BUFFER_CHUNK_SIZE 4096
#define DEFAULT_FILE_CHUNK_SIZE 65536

int64_t SendFile(SOCKET, const std::string &fileName, int chunkSize = DEFAULT_FILE_CHUNK_SIZE);
#endif //POWER_SENDING_FILE_H
