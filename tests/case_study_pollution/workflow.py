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
# load from CSV
stations_data = defaultdict(dict)
stations_file = "informacion_estaciones_red_calidad_aire.csv"

n_stations = 20

if os.path.exists(stations_file):
    with open(stations_file, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file, delimiter=';')
        for row in reader:
            station_id = int(row['CODIGO_CORTO'])
            stations_data[station_id] = {
                'direccion': row['DIRECCION'],
                'latitud': float(row['LATITUD']),
                'longitud': float(row['LONGITUD']),
                'altitud': float(row['ALTITUD'])
            }

            if len(stations_data.keys()) == n_stations:
                break


# Workflow definition

workflow = Workflow("airqualityworkflow", config_file="dagon-dynostore.ini", max_threads=1)

current_dir = os.path.dirname(os.path.abspath(__file__))

# *********** EDGE TASKS ************
edge_tasks = {}
for station_id in stations_data.keys():
    edge_tasks[station_id] = []
    for month in range(1, 12):  # months
        #for day in range(1, 30):  # days
        for day in range(1,2): #30):  # days
            #day = 1
            edge_id = f"edge_{station_id}_{month:02d}_{day:02d}"
            edge_tasks[station_id].append(edge_id)
            # Edge task command
            edge_cmd = f"python3 /home/cc/edge/ingest.py {day {month} {station_id} /home/cc/data/datos202412.csv {edge_id}.csv"
            task_edge = DagonTask(TaskType.BATCH, edge_id, edge_cmd, ssh_username="cc", ip="129.114.108.6", keypath="/home/cc/key_node.key")
            workflow.add_task(task_edge)


# print(edge_tasks)

# *********** FOG TASKS ************
fog_tasks = []

for station_id in edge_tasks.keys():
    fog_cmd = (
        "python3 " + current_dir + "/fog/merge.py --edge_csv_path { " +
        " ".join([f"workflow:///{eid}/airquality_{eid}.csv" for eid in edge_tasks[station_id]]) +
        " } --output_path fog_summary_" + str(station_id) + ".csv"
    )
    fog_id = f"fog_{station_id}"
    fog_tasks.append({"task_id": fog_id, "station_id": station_id})
    task_fog = DagonTask(TaskType.BATCH, fog_id, fog_cmd)
    workflow.add_task(task_fog)

# # *********** CLOUD TASKS ************
cloud_tasks = []

for i, fog_t in enumerate(fog_tasks):
    fog_id, station_id = fog_t["task_id"], fog_t["station_id"]
    cloud_cmd = (
        "python3 /home/ubuntu/cloud/aggregator.py --input workflow:///" + fog_id + "/fog_summary_" + str(station_id) + ".csv " +
        "--output monthly_avg_" + str(station_id) + ".csv " +
        "--alert alerts_" + str(station_id) + ".csv " +
        "--plots plots_" + str(station_id)
    )
    task_cloud = DagonTask(TaskType.BATCH, f"cloud_{station_id}", cloud_cmd, ssh_username="ubuntu", ip="13.51.172.116", keypath="/home/cc/key_node_aws.key")
    workflow.add_task(task_cloud)


# # Training and inference
training_cmd = f"python3 /home/ubuntu/cloud/train.py --data_dir /home/ubuntu/cloud/historical_data"
task_train = DagonTask(TaskType.BATCH, "train_model", training_cmd, ssh_username="ubuntu", ip="13.51.172.116", keypath="/home/cc/key_node_aws.key")
workflow.add_task(task_train)

# # Inference command
for station_id in stations_data.keys():
    inference_cmd = f"python3 /home/ubuntu/cloud/prediction.py --stations {station_id} --model workflow:///train_model/pollution_predictor_poly.pkl --features workflow:///train_model/poly_base_features.pkl --poly_transformer workflow:///train_model/poly_transformer.pkl  --data_dir /home/ubuntu/cloud/historical_data"
    task_inference = DagonTask(TaskType.BATCH, f"predict_pollution_{station_id}", inference_cmd, ssh_username="ubuntu", ip="13.51.172.116", keypath="/home/cc/key_node_aws.key")
    workflow.add_task(task_inference)

# Workflow execution
workflow.make_dependencies()
workflow.run()
