import os
import argparse
import shutil

m_argparser = argparse.ArgumentParser()

m_argparser.add_argument("-wn", "--workload_name", help="Workload name",
                         default="tmp")
m_argparser.add_argument("-b", "--build_path", help="Specify path to build directory",
                         default="build/")

m_args = m_argparser.parse_args()

check_build = os.path.exists('build')
check_logs = os.path.exists('log')
if not check_logs:
    os.mkdir('log')

finalDirPath ='log/' + m_args.workload_name
checkFinalDirPath = os.path.exists(finalDirPath)
if checkFinalDirPath:
    shutil.rmtree(finalDirPath)
    print("Old logs " + finalDirPath + " were removed")

os.mkdir(finalDirPath)
shutil.copyfile(m_args.build_path + "summary.txt", finalDirPath + "/summary.txt")
shutil.copyfile(m_args.build_path + "mlperf_log_detail.txt", finalDirPath + "/mlperf_log_detail.txt")
shutil.copyfile(m_args.build_path + "mlperf_log_accuracy.json", finalDirPath + "/mlperf_log_accuracy.json")
shutil.copyfile(m_args.build_path + "mlperf_log_summary.txt", finalDirPath + "/mlperf_log_summary.txt")




