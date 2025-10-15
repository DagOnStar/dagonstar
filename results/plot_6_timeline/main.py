import os
import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

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

def load_timelines(folder=".temp"):
    timelines = []
    for filename in os.listdir(folder):
        if filename.endswith(".json"):
            path = os.path.join(folder, filename)
            with open(path) as f:
                data = json.load(f)
            data["key"] = filename.replace(".timeline.json", "")
            timelines.append(data)
    return timelines

def plot_timeline(timeline):
    key = timeline["key"]
    events = []

    # Categories
    foreground_ops = {"Metadata registration", "Object transmission", "Catalog management", "metadata_register"}
    background_ops = {"Erasure coding", "Chunk upload"}

    all_starts = [
        v["start"] for v in timeline.values()
        if isinstance(v, dict) and "start" in v and "end" in v
    ]
    if not all_starts:
        print(f"Skipping {key}: no valid timing info.")
        return

    base_time_ns = min(all_starts)

    for name, info in timeline.items():
        if isinstance(info, dict) and "start" in info and "end" in info:
            start_s = (info["start"] - base_time_ns) / 1e9
            duration_s = (info["end"] - info["start"]) / 1e9
            events.append((name, start_s, duration_s))

    events.sort(key=lambda x: x[1])

    fig, ax = plt.subplots(figsize=(my_width, my_width / golden)) #plt.subplots(figsize=(10, 6))

    # Find bounds for grouped regions
    fg_start = min(start for name, start, _ in events if name in foreground_ops)
    fg_end = max(start + dur for name, start, dur in events if name in foreground_ops)
    bg_start = min(start for name, start, _ in events if name in background_ops)
    bg_end = max(start + dur for name, start, dur in events if name in background_ops)

    # Background regions
    ax.axvspan(fg_start, fg_end, color="#e6f2ff", alpha=0.5, label="Foreground (Client Waited)")
    ax.axvspan(bg_start, bg_end, color="#ffe6e6", alpha=0.5, label="Background (Passive Task)")

    for i, (name, start, duration) in enumerate(events):
        if name in foreground_ops:
            color = "#3399ff"
        elif name in background_ops:
            color = "#ff6666"
        else:
            color = "#999999"
        ax.barh(i, duration, left=start, height=0.5, color=color, edgecolor="black")
        ax.text(start + duration - 0.5, i, f"{duration:.1f}s", va="center", fontsize=8)

    ax.set_yticks(range(len(events)))
    ax.set_yticklabels([name for name, _, _ in events])

    # Client observed total time
    if "upload_total_perf_ns" in timeline:
        total_time_s = timeline["upload_total_perf_ns"] / 1e9
        ax.axvline(total_time_s, color="red", linestyle="--", linewidth=2)
        ax.text(total_time_s + 0.01, len(events) - 0.5,
                f"Response to client {total_time_s:.1f}s", color="red", va="center")

    # Legend
    legend_patches = [
        mpatches.Patch(color="#3399ff", label="Synchronous Task"),
        mpatches.Patch(color="#ff6666", label="Asynchronous Task"),
        #mpatches.Patch(color="#e6f2ff", alpha=0.5),#, label="Foreground Region"),
        #mpatches.Patch(color="#ffe6e6", alpha=0.5),#, label="Background Region"),
        #mpatches.Patch(color="red", linestyle="--", label="Client Total Time"),
    ]
    ax.legend(handles=legend_patches, loc="lower right", fontsize=8)

    ax.set_xlabel("Time (s)")
    #ax.set_title(f"Upload Timeline: {key}")
    ax.grid(True, axis='x', linestyle='--', alpha=0.3)
    plt.tight_layout()
    #plt.show()
    plt.savefig(f"{timeline["key"]}.timeline.pdf")


if __name__ == "__main__":
    timelines = load_timelines("times")
    print(timelines)
    for timeline in timelines:
        plot_timeline(timeline)
