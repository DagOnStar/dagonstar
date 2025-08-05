from dagon import Workflow
from dagon.task import DagonTask, TaskType
import json
import time
import csv
import os
import shutil
from collections import defaultdict
import statistics


# Stations data
#load from CSV
stations_data = defaultdict(dict)
stations_file = "informacion_estaciones_red_calidad_aire.csv"

if os.path.exists(stations_file):
    with open(stations_file, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file, delimiter=';')
        for row in reader:
            print(row)
            station_id = int(row['CODIGO_CORTO'])
            stations_data[station_id] = {
                'direccion': row['DIRECCION'],
                'latitud': float(row['LATITUD']),
                'longitud': float(row['LONGITUD']),
                'altitud': float(row['ALTITUD'])
            }


# Workflow definition

workflow = Workflow("airqualityworkflow", config_file="dagon.ini")

# *********** EDGE TASKS ************

for station_id in stations_data.keys():
    
    for month in range(1,12): #months
        for day in range(1,30): # days
            edge_id = f"edge_{station_id}_{month:02d}_{day:02d}"
            edge_cmd = f"python3 $PWD/edge/ingest.py {day} {month} {station_id}"
            task_edge = DagonTask(TaskType.BATCH, edge_id, edge_cmd)
            workflow.add_task(task_edge)


# Workflow execution
workflow.make_dependencies()
workflow.run()