import pandas as pd
import matplotlib.pyplot as plt


# --- Style setup ---
plt.style.use("../paper.mplstyle")
pt = 1. / 72.27
jour_sizes = {"PRD": {"onecol": 246. * pt, "twocol": 710. * pt}}
my_width = jour_sizes["PRD"]["twocol"]
golden = (1 + 5 ** 0.5) / 1
plt.rcParams.update({
    'axes.labelsize': 14,
    'legend.fontsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
})


# Load your dataset
df = pd.read_csv("results_failures_sum.csv")
object_size_mb = 1  # adjust if different

# Add storage cost and total MB stored
df["Storage_Cost"] = df["n"] / df["k"]
df["Total_MB_Stored"] = df["Storage_Cost"] * object_size_mb * 100

# Filter and sort by probability
df_10 = df[df["prob"] == 10].copy().sort_values(by="k")
df_50 = df[df["prob"] == 50].copy().sort_values(by="k")
df_70 = df[df["prob"] == 70].copy().sort_values(by="k")

# Start plot
fig, ax1 = plt.subplots(figsize=(my_width, my_width / golden))

# Line plots for Total Time
line_10, = ax1.plot(df_10["k"], df_10["Total_Time_s"], marker='o', linestyle='-', color='tab:blue', label="Total Time (10%)")
line_50, = ax1.plot(df_50["k"], df_50["Total_Time_s"], marker='D', linestyle='-', color='tab:purple', label="Total Time (50%)")
line_70, = ax1.plot(df_70["k"], df_70["Total_Time_s"], marker='^', linestyle='-', color='tab:orange', label="Total Time (70%)")

ax1.set_xlabel("k (Data Fragments)")
ax1.set_ylabel("Response Time (s)", color='black')
ax1.tick_params(axis='y', labelcolor='black')
ax1.grid(True, axis='y', linestyle='--', linewidth=0.5)

# Right Y-axis for storage
ax2 = ax1.twinx()
bar_storage = ax2.bar(df_10["k"], df_10["Total_MB_Stored"],
                      width=0.5, color='tab:green', alpha=0.4, label="Total Storage (MB)")

ax2.set_ylabel("Storage Overhead (MB)", color='tab:green')
ax2.tick_params(axis='y', labelcolor='tab:green')
ax2.spines['right'].set_visible(True)
ax2.spines['right'].set_color('gray')
ax2.spines['right'].set_linewidth(1.0)

# Combined legend at the top
lines = [line_10, line_50, line_70, bar_storage]
labels = ["FP (10\%)", "FP (50\%)", "FP (70\%)", "Total Storage (MB)"]
ax1.legend(lines, labels, loc='upper center', bbox_to_anchor=(0.5, 1.26), ncol=4, frameon=True)

# Layout and display
fig.tight_layout()
plt.savefig("storage_times_plot.pdf", bbox_inches='tight')
