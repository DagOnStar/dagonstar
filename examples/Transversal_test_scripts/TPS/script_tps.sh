#!/bin/sh
COMMANDDIR="/home/robot/Escritorio/Projects/Crawlers/Merra_Master/"
# 2 months static data download
mkdir -p ./outputDagon

python3 test_TPS.py $COMMANDDIR 2 2> ./outputDagon/tps_NI_output_2_tps.txt
python3 test_TPS.py $COMMANDDIR 3 2> ./outputDagon/tps_NI_output_3_tps.txt
python3 test_TPS.py $COMMANDDIR 4 2> ./outputDagon/tps_NI_output_4_tps.txt
python3 test_TPS.py $COMMANDDIR 5 2> ./outputDagon/tps_NI_output_5_tps.txt
python3 test_TPS.py $COMMANDDIR 6 2> ./outputDagon/tps_NI_output_6_tps.txt
python3 test_TPS.py $COMMANDDIR 7 2> ./outputDagon/tps_NI_output_7_tps.txt
python3 test_TPS.py $COMMANDDIR 8 2> ./outputDagon/tps_NI_output_8_tps.txt
python3 test_TPS.py $COMMANDDIR 9 2> ./outputDagon/tps_NI_output_9_tps.txt
python3 test_TPS.py $COMMANDDIR 10 2> ./outputDagon/tps_NI_output_10_tps.txt
python3 test_TPS.py $COMMANDDIR 11 2> ./outputDagon/tps_NI_output_11_tps.txt
python3 test_TPS.py $COMMANDDIR 12 2> ./outputDagon/tps_NI_output_12_tps.txt