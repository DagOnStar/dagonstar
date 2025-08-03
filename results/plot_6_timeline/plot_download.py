import os
import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

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

def load_timelines(filename):
        path = os.path.join(filename)
        with open(path) as f:
            data = json.load(f)
        data["key"] = filename.replace(".timeline.json", "")
        return data

def plot_timeline(timeline):
    key = timeline["key"]
    events = []

    all_starts = [
        v["start"] for v in timeline.values()
        if isinstance(v, dict) and "start" in v and "end" in v
    ]
    if not all_starts:
        print(f"Skipping {key}: no valid timing info.")
        return

    base_time_ns = min(all_starts)

    # Server-side events
    for name, info in timeline.items():
        if isinstance(info, dict) and "start" in info and "end" in info:
            start_s = (info["start"] - base_time_ns) / 1e9
            duration_s = (info["end"] - info["start"]) / 1e9
            events.append((name, start_s, duration_s))

    events.sort(key=lambda x: x[1])  # Sort by start time

    fig, ax = plt.subplots(figsize=(my_width, my_width / golden)) #plt.subplots(figsize=(10, 6))

    # Plot server-side event bars
    for i, (name, start, duration) in enumerate(events):
        ax.barh(i, duration, left=start, height=0.4)
        ax.text(start + duration + 0.01, i, f"{duration:.2f}s", va="center", fontsize=8)

    # Set y labels
    ax.set_yticks(range(len(events)))
    ax.set_yticklabels([name for name, _, _ in events])

    # Vertical line for client time
    if "pull_end" in timeline:
        total_time_s = (timeline["pull_end"] - timeline["pull_start"]) / 1e9
        print(total_time_s)
        ax.axvline(total_time_s, color="red", linestyle="--", linewidth=2, label="Client total time")
        ax.text(total_time_s + 0.01, len(events) - 0.5, f"Client total time\n{total_time_s:.2f}s",
                color="red", va="center", fontsize=9)

    ax.set_xlabel("Time (s)")
    ax.grid(True, axis='x', linestyle='--', alpha=0.5)
    ax.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(f"download_timeline.pdf")


if __name__ == "__main__":
    plot_timeline(load_timelines("download.json"))
