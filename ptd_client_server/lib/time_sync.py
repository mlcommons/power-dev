import ntplib  # type: ignore
import datetime
import logging
import time
import subprocess
import os
import sys
from typing import Callable


class RemouteHostSyncError(Exception):
    pass


class NtpIsEmptyError(Exception):
    pass


def get_ntp_time(server: str) -> float:
    try:
        ntp_client = ntplib.NTPClient()
        response = ntp_client.request(server, version=3)
        return response.tx_time
    except Exception:
        logging.exception(f"Can not get time from NTP server {server}")
        raise


def ntp_host_sync(server: str) -> bool:
    return remote_host_sync(lambda: get_ntp_time(server), lambda: ntp_sync(server))


def remote_host_sync(
    command: Callable[[], float], remote_recync: Callable[[], None]
) -> bool:
    try:
        if not validate_remote_time(command):
            remote_recync()
            return validate_remote_time(command)
    except Exception:
        logging.exception("Could not synchronize with remote host")
        return False
    return True


def validate_remote_time(command: Callable[[], float]) -> bool:
    time1 = time.time()
    remote_time = command()
    time2 = time.time()
    dt1 = 1000 * (time1 - remote_time)
    dt2 = 1000 * (time2 - remote_time)
    logging.info(f"The time difference is within range {dt1:.3f}ms..{dt2:.3f}ms")

    if max(abs(dt1), abs(dt2)) > 1000:
        logging.fatal(
            "The time difference between local and remote hosts is more than 1 second"
        )
        return False
    return True


def ntp_sync(server: str) -> None:
    logging.info(f"Synchronizing with {server!r} time using NTP...")

    if sys.platform == "win32":
        import win32api

        tx_time = get_ntp_time(server)
        try:
            utcTime = datetime.datetime.utcfromtimestamp(tx_time)
        except Exception:
            logging.exception("Can not convert NTP time to utc format")
            raise
        try:
            win32api.SetSystemTime(
                utcTime.year,
                utcTime.month,
                utcTime.weekday(),
                utcTime.day,
                utcTime.hour,
                utcTime.minute,
                utcTime.second,
                int(utcTime.microsecond / 1000),
            )
        except Exception:
            logging.exception(
                "Could not sync time using SetSystemTime windows time service."
            )
            raise
    else:
        command = ["ntpdate", "-b", "--", server]
        if os.getuid() != 0:
            command = ["sudo", "-n"] + command

        try:
            subprocess.run(command, input="", check=True)
        except Exception:
            logging.error("Could not sync time using ntpd.")
            raise
    # It could take sometime to set system time
    time.sleep(1)
