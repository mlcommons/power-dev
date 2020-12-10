import json
import argparse
import os

columnsAmount = 12
ampsColumnNumber = 5
voltsColumnNumber = 7
identSize = 4

data = {}
finalObject = {}

m_argparser = argparse.ArgumentParser()

m_argparser.add_argument("-spl", "--specpower_in", help="Specify PTDaemon power log dir (in custom PTD format)",
                         default="./tmp")
m_argparser.add_argument("-o", "--output_file", help="Specify output file with maximum Amps and Volts value",
                         default="maxAmpsVoltsValue.txt")

m_args = m_argparser.parse_args()

if m_args.specpower_in == m_args.output_file:
    print("**** ERROR: Power log output file cannot be the same as output file!")
    exit(1)

if m_args.specpower_in == "":
    print("**** ERROR: Power log input file parameter should not be empty")
    exit(1)

for filename in os.listdir(m_args.specpower_in):
    with open(m_args.specpower_in + "/" + filename, 'r') as outfile:
        lines = outfile.readlines()
        voltsInfo = []
        ampsInfo = []
        for line in lines:
            list = line.split(',')
            if len(list) == columnsAmount:
                voltsInfo.append(list[ampsColumnNumber])
                ampsInfo.append(list[voltsColumnNumber])
        data[filename] = {"maxAmps": max(ampsInfo), "maxVolts": max(voltsInfo)}


with open(m_args.output_file, 'w') as outfile:
    json.dump(data, outfile, indent=identSize)