#!/bin/sh
COMMANDDIR="/home/robot/Escritorio/Projects/Crawlers/Merra_Master/"
INITDATE="01-01-2019"
ENDATE="31-01-2019"

mkdir -p ./outputDagon

python3 transversal-docker-merra-multiworkflow.py $COMMANDDIR $INITDATE $ENDATE 1 2> ./outputDagon/output_1_workflow.txt
python3 transversal-docker-merra-multiworkflow.py $COMMANDDIR $INITDATE $ENDATE 2 2> ./outputDagon/output_2_workflow.txt
python3 transversal-docker-merra-multiworkflow.py $COMMANDDIR $INITDATE $ENDATE 3 2> ./outputDagon/output_3_workflow.txt
python3 transversal-docker-merra-multiworkflow.py $COMMANDDIR $INITDATE $ENDATE 4 2> ./outputDagon/output_4_workflow.txt
python3 transversal-docker-merra-multiworkflow.py $COMMANDDIR $INITDATE $ENDATE 5 2> ./outputDagon/output_5_workflow.txt
python3 transversal-docker-merra-multiworkflow.py $COMMANDDIR $INITDATE $ENDATE 6 2> ./outputDagon/output_6_workflow.txt
python3 transversal-docker-merra-multiworkflow.py $COMMANDDIR $INITDATE $ENDATE 7 2> ./outputDagon/output_7_workflow.txt
python3 transversal-docker-merra-multiworkflow.py $COMMANDDIR $INITDATE $ENDATE 8 2> ./outputDagon/output_8_workflow.txt
python3 transversal-docker-merra-multiworkflow.py $COMMANDDIR $INITDATE $ENDATE 9 2> ./outputDagon/output_9_workflow.txt
python3 transversal-docker-merra-multiworkflow.py $COMMANDDIR $INITDATE $ENDATE 10 2> ./outputDagon/output_10_workflow.txt
python3 transversal-docker-merra-multiworkflow.py $COMMANDDIR $INITDATE $ENDATE 11 2> ./outputDagon/output_11_workflow.txt
python3 transversal-docker-merra-multiworkflow.py $COMMANDDIR $INITDATE $ENDATE 12 2> ./outputDagon/output_12_workflow.txt
