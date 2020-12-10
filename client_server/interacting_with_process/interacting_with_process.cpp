//
// Created by julia on 04/12/2020.
//

#include "interacting_with_process.h"

#if defined(__clang__) || (defined(__GNUC__) && !defined(_WIN32))
int getProcIdByName(string procName) {
    int pid = -1;
    DIR *dp = nullptr;

   dp = opendir(kProcDir.c_str());
   if (dp == nullptr) {
     cerr << "Can not open " << kProcDir << endl;
     return pid;
   }

    struct dirent *dirp = nullptr;
    while (pid < 0 && (dirp = readdir(dp))) {
        int id = atoi(dirp->d_name);
        if (id > 0) {
            string cmdPath = kProcDir + dirp->d_name + kCmdlineDir;
            ifstream cmdFile(cmdPath.c_str());
            string cmdLine;
            getline(cmdFile, cmdLine);
            if (!cmdLine.empty()) {
                size_t pos = cmdLine.find('\0');
                if (pos != string::npos)
                    cmdLine = cmdLine.substr(0, pos);
                pos = cmdLine.rfind(kLinuxDelimiter);
                if (pos != string::npos)
                    cmdLine = cmdLine.substr(pos + 1);
                if (procName == cmdLine)
                    pid = id;
            }
        }
    }

    closedir(dp);

    return pid;
}
#endif

bool checkIfProcessExistsByName(string filename)
{
#if defined(__clang__) || (defined(__GNUC__) && !defined(_WIN32))
    return getProcIdByName(filename) > 0 ? true : false;
#elif defined(_MSC_VER) || defined(_WIN32)
    HANDLE hSnapShot = CreateToolhelp32Snapshot(TH32CS_SNAPALL, NULL);
    PROCESSENTRY32 pEntry;
    pEntry.dwSize = sizeof (pEntry);
    bool isProcessExists = false;
    BOOL hRes = Process32First(hSnapShot, &pEntry);
    while (hRes)
    {
        if (strcmp(pEntry.szExeFile, filename.c_str()) == 0)
        {
            HANDLE hProcess = OpenProcess(PROCESS_TERMINATE, 0,
                                          (DWORD) pEntry.th32ProcessID);
            if (hProcess != NULL)
            {
                isProcessExists = true;
                break;
            }
        }
        hRes = Process32Next(hSnapShot, &pEntry);
    }
    CloseHandle(hSnapShot);
    return isProcessExists;
#endif
}

#if defined(_MSC_VER) || defined(_WIN32)
bool executeSystemCommand(char *command_Line, STARTUPINFO *si, PROCESS_INFORMATION *pi) {
    ZeroMemory(si, sizeof(*si));
    si->cb = sizeof(si);
    ZeroMemory(pi, sizeof(*pi));

    if (!CreateProcess(NULL,
                       command_Line,
                       NULL,
                       NULL,
                       FALSE,
                       CREATE_NEW_CONSOLE,
                       NULL,
                       NULL,
                       si,
                       pi)
            ) {
        std::cerr << "CreateProcess failed " << GetLastError() << "Exit (1)" << std::endl;
        return (false);
    }
    return (true);
}

bool closeSystemProcess(PROCESS_INFORMATION *pi) {
    return TerminateProcess(pi->hProcess, 0) && CloseHandle(pi->hProcess) && CloseHandle(pi->hThread);
}
#endif