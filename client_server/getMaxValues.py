import json
import argparse

columnsAmount = 12
ampsColumnNumber = 5
voltsColumnNumber = 7
identSize = 4

voltsInfo = []
ampsInfo = []
data = {}

m_argparser = argparse.ArgumentParser()

m_argparser.add_argument("-spl", "--specpower_in", help="Specify PTDaemon power log file (in custom PTD format)",
                         default="")
m_argparser.add_argument("-o", "--output_file", help="Specify output file with maximum Amps and Volts value",
                         default="maxAmpsVoltsValue.txt")

m_args = m_argparser.parse_args()

if m_args.specpower_in == m_args.output_file:
    print("**** ERROR: Power log output file cannot be the same as output file!")
    exit(1)

if m_args.specpower_in == "":
    print("**** ERROR: Power log input file parameter should not be empty")
    exit(1)

with open(m_args.specpower_in, 'r') as outfile:
    lines = outfile.readlines()
    for line in lines:
        list = line.split(',')
        if len(list) == columnsAmount:
            voltsInfo.append(list[ampsColumnNumber])
            ampsInfo.append(list[voltsColumnNumber])

data = {"maxAmps": max(ampsInfo), "maxVolts": max(voltsInfo)}

with open(m_args.output_file, 'w') as outfile:
    json.dump(data, outfile, indent=identSize)
