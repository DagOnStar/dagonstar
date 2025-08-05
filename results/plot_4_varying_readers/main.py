import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# --- Style setup ---
plt.style.use("../paper.mplstyle")
# Load the CSV file
df = pd.read_csv("data.csv")  # Update path if needed

# Rename configurations for clarity
config_map = {
    "dagon.ini": "P2P transmission",
    "dagon-dynostore.ini": "Resilient Storage and Transmission"
}
df["config_label"] = df["config"].map(config_map)

# Compute throughput (requests per second)
df["throughput"] = df["num_objects"] / df["total_time_s"]


# Aggregate data by configuration and number of readers
agg_df = df.groupby(["config", "num_objects"]).agg({
    "total_time_s": "mean",
    "throughput": "mean"
}).reset_index()
agg_df["config_label"] = agg_df["config"].map(config_map)

# Split the aggregated data
df_ssh = agg_df[agg_df["config"] == "dagon.ini"]
df_dynostore = agg_df[agg_df["config"] == "dagon-dynostore.ini"]

# Prepare plot settings
pt = 1. / 72.27
jour_sizes = {"PRD": {"onecol": 246. * pt, "twocol": 510. * pt}}
my_width = jour_sizes["PRD"]["twocol"]
golden = (1 + 5 ** 0.5) / 1.5

sizes = df_ssh["num_objects"].values
x = np.arange(len(sizes))
width = 0.35

# Create plot
fig, ax1 = plt.subplots(figsize=(my_width, my_width / golden))

# Total time bars
bars1 = ax1.bar(x - width / 2,
                df_ssh["total_time_s"],
                width,
                label="P2P transmission",
                color="#A1C9F4")

bars2 = ax1.bar(x + width / 2,
                df_dynostore["total_time_s"],
                width,
                label="Resilient Storage and Transmission",
                color="#8DE5A1")

# Throughput lines
ax2 = ax1.twinx()
ax2.plot(x, df_ssh["throughput"], marker='o', color="#3978a8", label="Throughput (P2P)")
ax2.plot(x, df_dynostore["throughput"], marker='s', color="#2ca02c", label="Throughput (Resilient)")
print(df_dynostore)
# Axes and legends
ax1.set_ylabel('Average Response Time (s)')
ax2.set_ylabel('Average Throughput (requests/s)')
ax1.set_xlabel('Number of Concurrent Readers')
ax1.set_xticks(x)
ax1.set_xticklabels(sizes)
# Combine legends from both axes
lines_labels = ax1.get_legend_handles_labels()
lines2_labels = ax2.get_legend_handles_labels()
all_handles = lines_labels[0] + lines2_labels[0]
all_labels = lines_labels[1] + lines2_labels[1]
ax1.legend(all_handles, all_labels, loc='upper left', ncol=1, frameon=True)
ax1.grid(True, linestyle='--', alpha=0.6)
# Save the figure
plt.tight_layout()
plt.savefig("varying_readers.pdf")
#plt.show()
