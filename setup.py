#!/usr/bin/env python3
from distutils.core import setup

setup(
    name="mlcommons-power",
    version="1.1",
    author="The MLPerf Authors",
    packages=[
        "ptd_client_server",
        "ptd_client_server.lib",
        "ptd_client_server.lib.external",
        "ptd_client_server.tests.unit",
    ],
    scripts=[
        "bin/power_server",
        "bin/power_client",
        "bin/power_check",
        "compliance/sources_checksums.json",  # has to be in the same directory
    ],
    url="https://github.com/mlcommons/power-dev/",
    license="LICENSE.md",
    description="MLPerf Power Measurement",
    install_requires=[
        'pywin32;platform_system=="Windows"'
    ],
)
