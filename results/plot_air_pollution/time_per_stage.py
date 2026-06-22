import re
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.patches import Patch

from matplotlib import colormaps

# --- Style setup ---
plt.style.use("../paper.mplstyle")
pt = 1. / 72.27
jour_sizes = {"PRD": {"onecol": 246. * pt, "twocol": 510. * pt}}
my_width = jour_sizes["PRD"]["twocol"]
golden = (1 + 5 ** 0.5) / 1.3
plt.rcParams.update({
    'axes.labelsize': 14,
    'legend.fontsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
})

# File mapping
files_info = {
    "1_stations.txt": 1,
    "10_stations.txt": 10,
    "20_stations.txt": 20,
}

# Extract times
def extract_all_phases(filepath, station_count):
    with open(filepath, 'r') as f:
        content = f.read()

    patterns = [
        (r"(edge_\d+_\d+_\d+)\s+Completed in ([\d.]+) seconds", "Edge Tasks (Ingest daily data)"),
        (r"(fog_\d+)\s+Completed in ([\d.]+) seconds", "Fog Tasks (Merge per station)"),
        (r"(cloud_\d+)\s+Completed in ([\d.]+) seconds", "Cloud Tasks (Aggregate + Alert + Plot)"),
        (r"(train_model)\s+Completed in ([\d.]+) seconds", "Model training"),
        (r"(predict_pollution_\d+)\s+Completed in ([\d.]+) seconds", "Prediction")
    ]

    data = []
    for pattern, name in patterns:
        for match in re.findall(pattern, content):
            task_name, time_str = match
            data.append({
                "stations": station_count,
                "phase": name,
                "task": task_name,
                "time": float(time_str)
            })
    return data

# Load data
all_data = []
for filename, station_count in files_info.items():
    all_data.extend(extract_all_phases(filename, station_count))

df = pd.DataFrame(all_data)

# Group by station and phase: mean and std
df_bar = df.groupby(["stations", "phase"]).agg(
    avg_time=("time", "mean"),
    std_time=("time", "std")
).reset_index()

# Setup colors and hatches
phases = [
    "Edge Tasks (Ingest daily data)",
    "Fog Tasks (Merge per station)",
    "Cloud Tasks (Aggregate + Alert + Plot)",
    "Model training",
    "Prediction"
]

N = len(phases)
cmap = colormaps['turbo'].resampled(N)
colors = [cmap(i / (N - 1)) for i in range(N)]
hatches = ['///', '...', 'xxx', '\\\\', '+++']

palette = {phase: colors[i] for i, phase in enumerate(phases)}
hatch_map = {phase: hatches[i] for i, phase in enumerate(phases)}

# Plot
fig, ax = plt.subplots(figsize=(my_width, my_width / golden))
barplot = sns.barplot(
    data=df_bar,
    x="stations", y="avg_time", hue="phase",
    palette=palette,
    ax=ax,
    errorbar=None  # We’ll apply our own error bars
)

# Apply std error bars in gray
for (stations, phase), group in df_bar.groupby(["stations", "phase"]):
    idx = df_bar[(df_bar["stations"] == stations) & (df_bar["phase"] == phase)].index[0]
    patch = barplot.patches[idx]
    height = patch.get_height()
    x = patch.get_x() + patch.get_width() / 2
    err = group["std_time"].values[0]
    ax.errorbar(x, height, yerr=err, fmt='none', ecolor='gray', capsize=4, linewidth=1)

# Apply gray hatch on top of colored bars
for patch, (_, row) in zip(barplot.patches, df_bar.iterrows()):
    phase = row["phase"]
    hatch = hatch_map.get(phase, None)
    if hatch:
        patch.set_hatch(hatch)
        patch.set_edgecolor("white")  # Hatch line color
        patch.set_linewidth(0.7)


# Final touches
plt.xlabel("Number of Stations")
plt.ylabel("Avg. Response Time (s)")
ax.grid(True, axis='y', linestyle='--', linewidth=0.5)
# Rebuild legend with hatches
legend_patches = []
for phase in phases:
    legend_patches.append(Patch(
        facecolor=palette[phase],
        hatch=hatch_map[phase],
        edgecolor="white",
        label=phase,
        linewidth=0.7
    ))

# Replace seaborn legend
ax.legend(handles=legend_patches, ncols=2, frameon=True, fontsize=12)
plt.tight_layout()
plt.savefig("time_per_stage.pdf")
