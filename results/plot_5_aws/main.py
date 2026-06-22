import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# --- Style setup ---
plt.style.use("../paper.mplstyle")
pt = 1. / 72.27
jour_sizes = {"PRD": {"onecol": 246. * pt, "twocol": 510. * pt}}
my_width = jour_sizes["PRD"]["twocol"]
golden = (1 + 5 ** 0.5) / 1.5
plt.rcParams.update({
    'axes.labelsize': 14,
    'legend.fontsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
})


# Load the dataset
df = pd.read_csv("summary.csv")

# Ensure numeric types
df['file_size_mb'] = df['file_size_mb'].astype(float)
df['avg_time'] = df['avg_time'].astype(float)
df['std_dev'] = df['std_dev'].astype(float)

# Set up the plot
#fig, ax = plt.subplots(figsize=(my_width, my_width / golden)) #plt.subplots(figsize=(10, 6))
operations = df['operation'].unique()

fig, axes = plt.subplots(1, 2, figsize=(my_width, my_width / golden))

for i, op in enumerate(operations):
    ax = axes[i]
    subset = df[df['operation'] == op]

    for system in subset['system'].unique():
        sys_data = subset[subset['system'] == system]
        x = sys_data['file_size_mb'].values
        y = sys_data['avg_time'].values
        err = sys_data['std_dev'].values

        ax.plot(x, y, label=system, marker='o')
        ax.fill_between(x, y - err, y + err, alpha=0.3)

    ax.set_title(f'{op.capitalize()} Time vs File Size')
    ax.set_xlabel('File Size (MB)')
    ax.set_ylabel('Average Time (s)')
    
    ax.set_xscale('log')
    if i == 0:    
        ax.legend(fontsize=10)

plt.tight_layout()
#plt.show()
plt.savefig("aws_performance_comparison.pdf", bbox_inches='tight')