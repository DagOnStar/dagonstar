import re
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib import colormaps


# --- Style setup ---
plt.style.use("../paper.mplstyle")
pt = 1. / 72.27
jour_sizes = {"PRD": {"onecol": 246. * pt, "twocol": 510. * pt}}
my_width = jour_sizes["PRD"]["twocol"]
golden = (1 + 5 ** 0.5) / 1.1
plt.rcParams.update({
    'axes.labelsize': 14,
    'legend.fontsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
})

# Files and station counts
files_info = {
    "1_stations.txt": 1,
    "10_stations.txt": 10,
    "20_stations.txt": 20,
}

# Function to extract workflow timing
def extract_workflow_total_time(filepath, station_count):
    with open(filepath, 'r') as f:
        lines = f.readlines()

    start_time = None
    last_completion_time = None
    time_format = "%Y-%m-%d %H:%M:%S,%f"
    time_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})")

    for line in lines:
        if "Running workflow" in line and start_time is None:
            match = time_pattern.match(line)
            if match:
                start_time = pd.to_datetime(match.group(1), format=time_format)
        if "Completed in" in line:
            match = time_pattern.match(line)
            if match:
                last_completion_time = pd.to_datetime(match.group(1), format=time_format)

    if start_time and last_completion_time:
        total_time = (last_completion_time - start_time).total_seconds()
        return {"stations": station_count, "total_time": total_time}
    return None


# Gather results
results = []
for filename, station_count in files_info.items():
    res = extract_workflow_total_time(filename, station_count)
    if res:
        results.append(res)

# Create DataFrame
df_total = pd.DataFrame(results)
df_total["throughput"] = df_total["stations"] * 12 / df_total["total_time"]

print(df_total)

N = 2
cmap = colormaps['Paired'].resampled(N)
colors = [cmap(i / (N - 1)) for i in range(N)]  # Normalize i to [0,1] range

# Plot
fig, ax1 = plt.subplots(figsize=(my_width, my_width / golden))

# Left Y-axis: Total Time as bars
color1 = "#1f77b4"
ax1.set_xlabel("Number of Stations")
ax1.set_ylabel("Response Time (s)")#, color=colors[0])
bars = ax1.bar(df_total["stations"], df_total["total_time"], color=colors[0], width=1.5)
#ax1.tick_params(axis='y', labelcolor=colors[0])
ax1.grid(True, axis='y')

# Right Y-axis: Throughput as line
ax2 = ax1.twinx()
color2 = "#2ca02c"
ax2.set_ylabel("Throughput (tasks/s)", color=colors[1])
line = ax2.plot(df_total["stations"], df_total["throughput"], marker='s', color=colors[1], linewidth=2)
ax2.tick_params(axis='y', labelcolor=colors[1])


# Plot
#fig, ax1 = plt.subplots(figsize=(my_width, my_width / golden))
#sns.barplot(data=df_total, x="stations", y="total_time", palette="Paired")

#plt.title("Total Workflow Execution Time")
#plt.xlabel("Number of Stations")
#plt.ylabel("Response Time (s)")

# Combine legends from both axes
lines_labels = [*zip([bars], ["Response Time"]),
                *zip(line, ["Throughput"])]
handles, labels = zip(*lines_labels)
ax1.legend(handles, labels, loc="best", frameon=True, ncols=1)


ax1.grid(True, axis='y', linestyle='--', linewidth=0.5)
plt.tight_layout()
plt.savefig("total_time.pdf")
