import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# --- Style setup ---
plt.style.use("../paper.mplstyle")
pt = 1. / 72.27
jour_sizes = {"PRD": {"onecol": 246. * pt, "twocol": 510. * pt}}
my_width = jour_sizes["PRD"]["twocol"]
golden = (1 + 5 ** 0.5) / 1
plt.rcParams.update({
    'axes.labelsize': 14,
    'legend.fontsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
})


# Load the CSV file
df = pd.read_csv("data.csv")

# Rename configurations for clarity
config_map = {
    "dagon.ini": "SCP: point-to-point transmission",
    "dagon-dynostore.ini": "DynoStore: Resilient Storage \n and Transmission"
}
df["config_label"] = df["config"].map(config_map)

# Sort for consistent plotting
df = df.sort_values(by=["object_size_MB", "config_label"])

# Group by size and label for plotting
sizes = df["object_size_MB"].unique()
labels = df["label"].unique()

# Prepare plot data
x = np.arange(len(sizes))  # the label locations
width = 0.35  # the width of the bars


fig, ax = plt.subplots(figsize=(my_width, my_width / golden)) #plt.subplots(figsize=(10, 6))

# Extract SSH and DynoStore separately
df_ssh = df[df["config"] == "dagon.ini"]
df_dynostore = df[df["config"] == "dagon-dynostore.ini"]

print(df_ssh)

# Plot bars
bars1 = ax.bar(x - width / 2,
               df_ssh["mean_total_time_s"],
               width,
               yerr=df_ssh["std_total_time_s"],
               capsize=5,
               label=df_ssh["config_label"].iloc[0],
               color="#A1C9F4")

bars2 = ax.bar(x + width / 2,
               df_dynostore["mean_total_time_s"],
               width,
               yerr=df_dynostore["std_total_time_s"],
               capsize=5,
               label=df_dynostore["config_label"].iloc[0],
               color="#8DE5A1")

# Add labels and formatting
ax.set_ylabel('Avgerage \n Response Time (s)')
ax.set_xlabel('Data Size (MB)')
ax.set_xticks(x)
ax.set_xticklabels(df_ssh["object_size_MB"])
ax.legend( frameon=True)
ax.grid(True, linestyle='--', alpha=0.6)

# Save the figure
plt.tight_layout()
plt.savefig("oneW_nR.pdf")
#plt.show()
