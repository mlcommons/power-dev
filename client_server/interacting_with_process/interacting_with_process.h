//
// Created by julia on 04/12/2020.
//

#ifndef POWER_INTERACTING_WITH_PROCESS_H
#define POWER_INTERACTING_WITH_PROCESS_H


#include <string>

#if defined(__clang__) || (defined(__GNUC__) && !defined(_WIN32))
#include <sys/types.h>
#include <dirent.h>
#include <errno.h>
#include <vector>
#include <iostream>
#include <fstream>
#include <stdlib.h>
#include <stdio.h>
#include <signal.h>
#elif defined(_MSC_VER) || defined(_WIN32)
#include <windows.h>
#include <process.h>
#include <Tlhelp32.h>
#include <winbase.h>
#endif

using namespace std;

#if defined(__clang__) || (defined(__GNUC__) && !defined(_WIN32))
const string kProcDir = "/proc/";
const string kCmdlineDir = "/cmdline";
const char kLinuxDelimiter = '/';
#endif

#endif //POWER_INTERACTING_WITH_PROCESS_H
