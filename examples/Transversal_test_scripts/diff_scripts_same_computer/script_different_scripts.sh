#!/bin/sh
COMMANDDIR="/home/robot/Escritorio/Projects/Crawlers/Merra_Master/"
INITDATE="01-01-2019"
ENDATE="31-01-2019"

mkdir -p ./outputDagon


python3 Dif_scripts.py $COMMANDDIR $INITDATE $ENDATE 2 2> ./outputDagon/DS_output_2_workflow.txt
python3 Dif_scripts.py $COMMANDDIR $INITDATE $ENDATE 3 2> ./outputDagon/DS_output_3_workflow.txt
python3 Dif_scripts.py $COMMANDDIR $INITDATE $ENDATE 4 2> ./outputDagon/DS_output_4_workflow.txt
python3 Dif_scripts.py $COMMANDDIR $INITDATE $ENDATE 5 2> ./outputDagon/DS_output_5_workflow.txt
python3 Dif_scripts.py $COMMANDDIR $INITDATE $ENDATE 6 2> ./outputDagon/DS_output_6_workflow.txt
python3 Dif_scripts.py $COMMANDDIR $INITDATE $ENDATE 7 2> ./outputDagon/DS_output_7_workflow.txt
python3 Dif_scripts.py $COMMANDDIR $INITDATE $ENDATE 8 2> ./outputDagon/DS_output_8_workflow.txt
python3 Dif_scripts.py $COMMANDDIR $INITDATE $ENDATE 9 2> ./outputDagon/DS_output_9_workflow.txt
python3 Dif_scripts.py $COMMANDDIR $INITDATE $ENDATE 10 2> ./outputDagon/DS_output_10_workflow.txt
python3 Dif_scripts.py $COMMANDDIR $INITDATE $ENDATE 11 2> ./outputDagon/DS_output_11_workflow.txt
python3 Dif_scripts.py $COMMANDDIR $INITDATE $ENDATE 12 2> ./outputDagon/DS_output_12_workflow.txt