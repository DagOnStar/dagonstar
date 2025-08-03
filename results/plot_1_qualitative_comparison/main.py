import matplotlib.pyplot as plt
import numpy as np

# --- Style setup ---
plt.style.use("../paper.mplstyle")
pt = 1. / 72.27
jour_sizes = {"PRD": {"onecol": 246. * pt, "twocol": 510. * pt}}
my_width = jour_sizes["PRD"]["twocol"]
golden = (1 + 5 ** 0.5) / .5
plt.rcParams.update({
    'axes.labelsize': 14,
    'legend.fontsize': 14,
    'xtick.labelsize': 11,
    'ytick.labelsize': 10,
})

# === Define categories ===
transfer_categories = [
    "Transfer\nEfficiency",
    "WAN\nTransference",
    "Multi-\nReader\nSupport",
    "Fragmentation\nAwareness",
    "Security\n\\& Access\nControl",
    "Data\nIntegrity"
]

storage_categories = [
    "Storage\nResilience",
    "Reuse\nAcross\n DAGs",
    "Lifecycle\nManagement",
    "Workflow\nIntegration",
    "Security\n\\& Access\nControl"
]

# === Radar angles ===
def compute_angles(n):
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]
    return angles

transfer_angles = compute_angles(len(transfer_categories))
storage_angles = compute_angles(len(storage_categories))

# === Tool Scores ===
transfer_scores = {
    "SSH": [5, 3, 2, 1, 5, 5],
    "S3": [3, 5, 5, 1, 5, 5],
    "DynoStore": [4, 5, 5, 5, 5, 5],
    "Globus/GridFTP": [4, 5, 4, 2, 5, 5],
    "IPFS": [2, 4, 3, 4, 3, 3]
}

storage_scores = {
    "S3": [5, 3, 5, 2, 5],
    "DynoStore": [5, 5, 4, 5, 4],
    "IPFS": [3, 3, 2, 2, 2]
}

# === Pastel colors ===
pastel_colors = {
    "SSH": "#A1C9F4",
    "S3": "#FFB482",
    "DynoStore": "#8DE5A1",
    "Globus/GridFTP": "#CBA6E3",
    "IPFS": "#FF9F9B"
}

# === Create subplots ===
fig, axs = plt.subplots(ncols=2, figsize=(10, 6), subplot_kw=dict(polar=True))

plt.subplots_adjust(wspace=0.35)

# === Radar plot helper ===
def plot_radar(ax, angles, categories, scores_dict, title):
    num_tools = len(scores_dict)
    max_alpha = 0.6
    min_alpha = 0.2
    alpha_values = np.linspace(max_alpha, min_alpha, num_tools)

    for idx, (tool, scores) in enumerate(scores_dict.items()):
        values = scores + scores[:1]
        alpha = alpha_values[idx]
        ax.plot(angles, values, label=tool, color=pastel_colors[tool], linewidth=2, marker='o', markersize=6)
        ax.fill(angles, values, color=pastel_colors[tool], alpha=alpha)

    ax.set_title(title)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_thetagrids(np.degrees(angles[:-1]), categories, fontsize=11)
    ax.set_ylim(0, 5)
    ax.set_yticks([1, 3, 5])
    ax.grid(True, linestyle='--', linewidth=0.5, color='gray')

# === Plot each radar chart ===
plot_radar(axs[0], transfer_angles, transfer_categories, transfer_scores, r"\textbf{Data Transfer Capabilities}")
plot_radar(axs[1], storage_angles, storage_categories, storage_scores, r"\textbf{Data Storage Capabilities}")

# === Bring category labels forward ===
for ax in axs:
    for label in ax.get_xticklabels():
        label.set_zorder(40)
        label.set_bbox(dict(facecolor='white', alpha=0.9, edgecolor='none', boxstyle='round,pad=0.2'))

# === Shared legend below both plots ===
handles, labels = axs[0].get_legend_handles_labels()
fig.legend(
    handles, labels,
    loc='upper center',
    #bbox_to_anchor=(0.5, -0.1),
    ncol=1,
    frameon=True, facecolor='white', edgecolor='black',
    fontsize=11
)

axs[0].tick_params(pad=20)  # For transfer plot
axs[1].tick_params(pad=20)  # For storage plot

# === Final layout and save ===
plt.tight_layout()
plt.subplots_adjust(bottom=0.25)

fig.text(
    0.6, 0.22,  # X, Y position (normalized figure coordinates)
    r"\textbf{Scale}: \textbf{1} = No Support  \textbf{3} = Possible with limitations  \textbf{5} = Native",
    ha='left', va='center',
    fontsize=11,
    style='italic',
    bbox=dict(
        facecolor='white',
        edgecolor='black',
        boxstyle='round,pad=0.4',
        alpha=0.9
    )
)

plt.savefig("qualitative.pdf", bbox_inches='tight')
#plt.show()
