#!/usr/bin/env python3
"""
Metrics Analysis Tools
Analyze energy and performance metrics from MongoDB
"""

import configparser
from pymongo import MongoClient
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import json


class EnergyAnalyzer:
    def __init__(self, config_file='dagon.ini'):
        """
        Load MongoDB connection settings from dagon.ini
        """
        config = configparser.ConfigParser()
        config.read(config_file)

        self.mongo_uri = config.get('mongodb', 'uri')
        self.db_name = config.get('mongodb', 'database')
        self.collection_name = config.get('mongodb', 'collection')

    def get_collection(self):
        """
        Return MongoDB collection handle + client
        """
        client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
        db = client[self.db_name]
        return db[self.collection_name], client

    def show_energy_summary(self, limit=10):
        """
        Print a summary of recent executions:
        - total duration
        - energy (RasPi + PC)
        - number of processed records
        """
        collection, client = self.get_collection()

        # Only executions where energy monitoring was stored
        cursor = collection.find(
            {"energy_monitoring.enabled": True}
        ).sort("export_timestamp", -1).limit(limit)

        docs = list(cursor)

        if not docs:
            print("No executions with energy metrics found")
            client.close()
            return

        print("\n" + "=" * 100)
        print(f"⚡ ENERGY SUMMARY (Last {len(docs)} executions)")
        print("=" * 100)

        print(f"\n{'Execution ID':<20} {'Duration':<10} "
              f"{'RasPi':<15} {'PC':<15} {'Total':<15} {'Records':<10}")
        print(f"{'':20} {'(s)':10} {'Energy (Wh)':15} "
              f"{'Energy (Wh)':15} {'Energy (Wh)':15} {'':10}")
        print("-" * 100)

        for doc in docs:
            exec_id = doc.get('execution_id', 'unknown')
            duration = doc.get('total_duration_seconds', 0)
            records = doc.get('summary', {}).get('count', 0)

            energy_mon = doc.get('energy_monitoring', {})
            rpi_energy = energy_mon.get('raspberry_pi', {}).get('energy', {}).get('total_wh', 0)
            pc_energy = energy_mon.get('pc', {}).get('energy', {}).get('total_wh', 0)
            total_energy = rpi_energy + pc_energy

            print(f"{exec_id:<20} {duration:<10.2f} "
                  f"{rpi_energy:<15.4f} {pc_energy:<15.4f} "
                  f"{total_energy:<15.4f} {records:<10}")

        # Aggregate energy over all listed executions
        total_rpi = sum(
            doc.get('energy_monitoring', {})
               .get('raspberry_pi', {})
               .get('energy', {})
               .get('total_wh', 0)
            for doc in docs
        )
        total_pc = sum(
            doc.get('energy_monitoring', {})
               .get('pc', {})
               .get('energy', {})
               .get('total_wh', 0)
            for doc in docs
        )

        print("-" * 100)
        print(f"{'TOTAL:':<20} {'':10} "
              f"{total_rpi:<15.4f} {total_pc:<15.4f} "
              f"{total_rpi + total_pc:<15.4f}")
        print("=" * 100 + "\n")

        client.close()

    def compare_energy_efficiency(self, execution_ids=None, limit=5):
        """
        Compare energy efficiency across executions:
        - mWh per processed record
        """
        collection, client = self.get_collection()

        if execution_ids:
            cursor = collection.find({"execution_id": {"$in": execution_ids}})
        else:
            cursor = collection.find(
                {"energy_monitoring.enabled": True}
            ).sort("export_timestamp", -1).limit(limit)

        docs = list(cursor)

        if not docs:
            print("No executions found for comparison")
            client.close()
            return

        print("\n" + "=" * 110)
        print(f"📊 ENERGY EFFICIENCY COMPARISON ({len(docs)} executions)")
        print("=" * 110)

        data = []
        for doc in docs:
            exec_id = doc.get('execution_id', 'unknown')
            records = doc.get('summary', {}).get('count', 0)

            # Skip executions without processed data
            if records == 0:
                continue

            energy_mon = doc.get('energy_monitoring', {})
            rpi_energy = energy_mon.get('raspberry_pi', {}).get('energy', {}).get('total_wh', 0)
            pc_energy = energy_mon.get('pc', {}).get('energy', {}).get('total_wh', 0)
            total_energy = rpi_energy + pc_energy

            # mWh per record (energy per processed sample)
            efficiency = (total_energy / records) * 1000

            data.append({
                'execution_id': exec_id,
                'records': records,
                'duration': doc.get('total_duration_seconds', 0),
                'rpi_energy_wh': rpi_energy,
                'pc_energy_wh': pc_energy,
                'total_energy_wh': total_energy,
                'efficiency_mwh_per_record': efficiency
            })

        # Best (lowest mWh/record) first
        data.sort(key=lambda x: x['efficiency_mwh_per_record'])

        print(f"\n{'Rank':<6} {'Execution ID':<20} {'Records':<10} "
              f"{'Energy (Wh)':<15} {'Efficiency':<20}")
        print(f"{'':6} {'':20} {'':10} {'':15} {'(mWh/record)':20}")
        print("-" * 110)

        for i, item in enumerate(data, 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
            print(f"{i:<6} {item['execution_id']:<20} {item['records']:<10} "
                  f"{item['total_energy_wh']:<15.4f} "
                  f"{item['efficiency_mwh_per_record']:<20.3f} {emoji}")

        print("=" * 110 + "\n")

        client.close()
        return data

    def export_energy_to_csv(self, output_file="energy_analysis.csv", limit=None):
        """
        Export per-execution metrics to CSV:
        - duration (deployment / workflow time)
        - energy (RasPi + PC)
        - CPU and RAM usage
        """
        collection, client = self.get_collection()

        query = {"energy_monitoring.enabled": True}
        cursor = collection.find(query).sort("export_timestamp", -1)

        if limit:
            cursor = cursor.limit(limit)

        docs = list(cursor)

        rows = []
        for doc in docs:
            energy_mon = doc.get('energy_monitoring', {})

            row = {
                'execution_id': doc.get('execution_id'),
                'timestamp': doc.get('export_timestamp'),
                'raspberry_pi': doc.get('raspberry_pi'),
                'duration_seconds': doc.get('total_duration_seconds', 0),
                'records_count': doc.get('summary', {}).get('count', 0),
                'successful': doc.get('all_tasks_successful', False),

                # Task durations (deployment / processing time per task)
                'task_A_duration': doc.get('metrics', {}).get('task_A_task_duration', 0),
                'task_B_duration': doc.get('metrics', {}).get('task_B_task_duration', 0),

                # RasPi energy + CPU + RAM
                'rpi_power_mean_w': energy_mon.get('raspberry_pi', {}).get('power', {}).get('mean_watts', 0),
                'rpi_power_max_w': energy_mon.get('raspberry_pi', {}).get('power', {}).get('max_watts', 0),
                'rpi_cpu_mean_pct': energy_mon.get('raspberry_pi', {}).get('cpu', {}).get('mean_percent', 0),
                'rpi_cpu_max_pct': energy_mon.get('raspberry_pi', {}).get('cpu', {}).get('max_percent', 0),
                'rpi_ram_mean_pct': energy_mon.get('raspberry_pi', {}).get('ram', {}).get('mean_percent', 0),
                'rpi_ram_max_pct': energy_mon.get('raspberry_pi', {}).get('ram', {}).get('max_percent', 0),
                'rpi_temp_mean_c': energy_mon.get('raspberry_pi', {}).get('temperature', {}).get('mean_celsius', 0),
                'rpi_energy_wh': energy_mon.get('raspberry_pi', {}).get('energy', {}).get('total_wh', 0),

                # PC energy + CPU (RAM mean could be added similarly)
                'pc_power_mean_w': energy_mon.get('pc', {}).get('power', {}).get('mean_watts', 0),
                'pc_power_max_w': energy_mon.get('pc', {}).get('power', {}).get('max_watts', 0),
                'pc_cpu_mean_pct': energy_mon.get('pc', {}).get('cpu', {}).get('mean_percent', 0),
                'pc_energy_wh': energy_mon.get('pc', {}).get('energy', {}).get('total_wh', 0),

                # Sensor stats (optional but useful for correlating workload with energy)
                'mean_temp_c': doc.get('summary', {}).get('mean_temp_c', 0),
                'mean_humidity': doc.get('summary', {}).get('mean_humidity', 0),
            }
            rows.append(row)

        df = pd.DataFrame(rows)
        df.to_csv(output_file, index=False)

        print(f"✅ Exported {len(rows)} executions to {output_file}")
        client.close()
        return df

    def plot_energy_trends(self, limit=20):
        """
        Plot trends for:
        - total energy per execution
        - RasPi vs PC energy
        - mean power
        - CPU usage
        - energy efficiency (mWh/record)
        - relationship between duration and total energy
        """
        df = self.export_energy_to_csv("temp_energy.csv", limit)

        # Prepare X-axis labels starting from 1
        x_indices = range(1, len(df) + 1)

        fig, axes = plt.subplots(3, 2, figsize=(15, 12))

        # 1. Total energy consumption per execution
        ax = axes[0, 0]
        df['total_energy_wh'] = df['rpi_energy_wh'] + df['pc_energy_wh']
        ax.bar(x_indices, df['total_energy_wh'], color='steelblue', alpha=0.7)
        ax.set_xlabel('Execution Number')
        ax.set_ylabel('Energy (Wh)')
        ax.set_title('Total Energy Consumption per Execution')
        ax.set_xticks(x_indices) # Force integer ticks
        ax.grid(True, alpha=0.3)

        # 2. RasPi vs PC energy distribution
        ax = axes[0, 1]
        ax.bar(x_indices, df['rpi_energy_wh'], label='Raspberry Pi', alpha=0.7)
        ax.bar(x_indices, df['pc_energy_wh'], bottom=df['rpi_energy_wh'], label='PC', alpha=0.7)
        ax.set_xlabel('Execution Number')
        ax.set_ylabel('Energy (Wh)')
        ax.set_title('Energy Distribution: RasPi vs PC')
        ax.set_xticks(x_indices) # Force integer ticks
        ax.legend()
        ax.grid(True, alpha=0.3)

        # 3. Mean power (W)
        ax = axes[1, 0]
        ax.plot(x_indices, df['rpi_power_mean_w'], 'o-', label='RasPi Mean Power', linewidth=2)
        ax.plot(x_indices, df['pc_power_mean_w'], 's-', label='PC Mean Power', linewidth=2)
        ax.set_xlabel('Execution Number')
        ax.set_ylabel('Power (W)')
        ax.set_title('Mean Power Consumption')
        ax.set_xticks(x_indices) # Force integer ticks
        ax.legend()
        ax.grid(True, alpha=0.3)

        # 4. CPU usage (%)
        ax = axes[1, 1]
        ax.plot(x_indices, df['rpi_cpu_mean_pct'], 'o-', label='RasPi CPU %', linewidth=2)
        ax.plot(x_indices, df['pc_cpu_mean_pct'], 's-', label='PC CPU %', linewidth=2)
        ax.set_xlabel('Execution Number')
        ax.set_ylabel('CPU %')
        ax.set_title('CPU Utilization')
        ax.set_xticks(x_indices) # Force integer ticks
        ax.legend()
        ax.grid(True, alpha=0.3)

        # 5. Energy efficiency (mWh per record)
        ax = axes[2, 0]
        df['efficiency'] = (df['total_energy_wh'] / df['records_count']) * 1000
        ax.plot(x_indices, df['efficiency'], 'o-', color='green', linewidth=2)
        ax.set_xlabel('Execution Number')
        ax.set_ylabel('mWh per Record')
        ax.set_title('Energy Efficiency')
        ax.set_xticks(x_indices) # Force integer ticks
        ax.grid(True, alpha=0.3)

        # 6. Duration vs energy (colored by number of records)
        ax = axes[2, 1]
        scatter = ax.scatter(
            df['duration_seconds'],
            df['total_energy_wh'],
            c=df['records_count'],
            cmap='viridis',
            s=100,
            alpha=0.7
        )
        ax.set_xlabel('Duration (s)')
        ax.set_ylabel('Energy (Wh)')
        ax.set_title('Duration vs Energy (colored by records count)')
        plt.colorbar(scatter, ax=ax, label='Records')
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig('energy_trends.png', dpi=300, bbox_inches='tight')
        print("✅ Plots saved to: energy_trends.png")
        # plt.show()  # Commented out to prevent hanging in terminal


def main():
    import sys

    analyzer = EnergyAnalyzer()

    if len(sys.argv) < 2:
        print("Energy Analysis Tools")
        print("=" * 70)
        print("\nUsage:")
        print("  python3 metrics_analysis_tools.py summary [limit]")
        print("  python3 metrics_analysis_tools.py compare [limit]")
        print("  python3 metrics_analysis_tools.py export [output.csv]")
        print("  python3 metrics_analysis_tools.py plot [limit]")
        print("\nExamples:")
        print("  python3 metrics_analysis_tools.py summary 10")
        print("  python3 metrics_analysis_tools.py compare 5")
        print("  python3 metrics_analysis_tools.py export energy_data.csv")
        print("  python3 metrics_analysis_tools.py plot 20")
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "summary":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            analyzer.show_energy_summary(limit)

        elif command == "compare":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            analyzer.compare_energy_efficiency(limit=limit)

        elif command == "export":
            output = sys.argv[2] if len(sys.argv) > 2 else "energy_analysis.csv"
            analyzer.export_energy_to_csv(output)

        elif command == "plot":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
            analyzer.plot_energy_trends(limit)

        else:
            print(f"Unknown command: {command}")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
