import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

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


# --- Load your summary CSV file ---
csv_path = "results_failures_sum.csv"  # Adjust path as needed
df = pd.read_csv(csv_path)

# --- Calculate success rate and identify optimal configurations ---
df["Success_Rate"] = df["Successes"] / df["Total_Operations"]
df["Storage_Cost"] = df["n"] / df["k"]  # Only used for filtering

# Create pivot table for heatmap
success_data = df.pivot(index="k", columns="prob", values="Success_Rate")

# Identify optimal configurations (for highlighting)
optimal_mask = (success_data >= 0.95) & (df.pivot(index="k", columns="prob", values="Storage_Cost") <= 2.0)

# --- Create the heatmap ---
fig, axes = plt.subplots(figsize=(my_width, my_width / golden))

# Success rate as percentage annotations
success_pct = (success_data * 100).round(1)
ax = sns.heatmap(success_data, annot=success_pct.astype(str) + '\%', fmt="",
                 cmap="Blues", linewidths=0.5, linecolor='gray',
                 cbar_kws={'label': 'Success Rate'})

# Set y-tick labels to just 'k'
ax.set_yticklabels(sorted(df["k"].unique()), rotation=0)

# Highlight optimal configurations with red boxes
for y in range(success_data.shape[0]):
    for x in range(success_data.shape[1]):
        if optimal_mask.iloc[y, x]:
            ax.add_patch(plt.Rectangle((x, y), 1, 1, fill=False, edgecolor='red', lw=2))

# Final plot settings
#plt.title("Success Rate Heatmap by (k, Failure Probability)")
plt.xlabel("Failure Probability (\%)")
plt.ylabel("k (Data Fragments)")
plt.tight_layout()
plt.savefig("success_rate_heatmap.pdf")
