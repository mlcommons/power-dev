#include "sending_file.h"

int64_t GetFileSize(const std::string &fileName) {
    FILE *f;
    if ((f = fopen(fileName.c_str(), "rb")) == NULL) {
        return -1;
    }
    fseek(f, 0, SEEK_END);
    const int64_t len = ftell(f);
    fclose(f);
    return len;
}

int SendBuffer(SOCKET s, const char *buffer, int bufferSize, int chunkSize = DEFAULT_BUFFER_CHUNK_SIZE) {
    int allSendedBytes = 0;
    while (allSendedBytes < bufferSize) {
        const int sendedBytes = send(s, &buffer[allSendedBytes], std::min(chunkSize, bufferSize - allSendedBytes), 0);
        if (sendedBytes < 0) {
            return sendedBytes;
        }
        allSendedBytes += sendedBytes;
    }
    return allSendedBytes;
}

int64_t SendFile(SOCKET s, const std::string &fileName, int chunkSize) {
    const int64_t fileSize = GetFileSize(fileName);

    if (fileSize < 0) {
        std::cerr << "Can not get file size" << std::endl;
        return 1;
    }

    std::ifstream file(fileName, std::ifstream::binary);
    if (file.fail()) {
        std::cerr << "Can not open ifstream" << std::endl;
        return 1;
    }

    if (SendBuffer(s, reinterpret_cast<const char *>(&fileSize),
                   sizeof(fileSize)) != sizeof(fileSize)) {
        std::cerr << "Can not send file size" << std::endl;
        return 1;
    }

    char *buffer = new char[chunkSize];
    bool errored = false;
    int64_t i = fileSize;
    while (i != 0) {
        const int64_t ssize = std::min(i, (int64_t) chunkSize);
        if (!file.read(buffer, ssize)) {
            errored = true;
            break;
        }
        const int l = SendBuffer(s, buffer, (int) ssize);
        if (l < 0) {
            errored = true;
            break;
        }
        i -= l;
    }
    delete[] buffer;
    if (!errored) {
        std::cout << "Send file to client" << std::endl;
    } else {
        std::cerr << "Can not send file to client" << std::endl;
    }

    file.close();

    return errored ? 1 : fileSize;
}
