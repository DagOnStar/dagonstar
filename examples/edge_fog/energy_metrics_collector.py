#!/usr/bin/env python3
"""
Energy Metrics Collector for Dagon Workflows
Captures CPU, RAM, and energy metrics from Prometheus during workflow execution
"""

import requests
import time
from datetime import datetime, timezone
import threading
import json
from typing import Dict, List, Optional

class PrometheusMetricsCollector:
    """Metrics collector from Prometheus during workflow execution"""
    
    def __init__(self, prometheus_url: str = "http://localhost:9090", 
                 sampling_interval: int = 5):
        """
        Args:
            prometheus_url: Prometheus URL
            sampling_interval: Sampling interval in seconds
        """
        self.prometheus_url = prometheus_url
        self.sampling_interval = sampling_interval
        self.metrics_data = []
        self.is_collecting = False
        self.collection_thread = None
        self.start_time = None
        self.end_time = None
        
    def query_prometheus(self, query: str) -> Optional[float]:
        """Executes a query in Prometheus and returns the value"""
        try:
            response = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={'query': query},
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'success' and data['data']['result']:
                    return float(data['data']['result'][0]['value'][1])
            return None
        except Exception as e:
            print(f"Warning: Error querying Prometheus: {e}")
            return None
    
    def collect_metrics_once(self) -> Dict:
        """Captures a snapshot of all metrics"""
        timestamp = time.time()
        
        metrics = {
            'timestamp': timestamp,
            'datetime': datetime.fromtimestamp(timestamp).isoformat(),
        }
        
        # === RASPBERRY PI METRICS ===
        rpi_power = self.query_prometheus('rpi_pmic_power_watts')
        if rpi_power:
            metrics['rpi_power_watts'] = rpi_power
        
        rpi_cpu = self.query_prometheus(
            '100 - (avg by (instance) (rate(node_cpu_seconds_total{job="node-rpi",mode="idle"}[30s])) * 100)'
        )
        if rpi_cpu:
            metrics['rpi_cpu_percent'] = rpi_cpu
        
        rpi_ram = self.query_prometheus(
            '100 * (1 - ((node_memory_MemAvailable_bytes{job="node-rpi"} or '
            'node_memory_Buffers_bytes{job="node-rpi"} + node_memory_Cached_bytes{job="node-rpi"} + '
            'node_memory_MemFree_bytes{job="node-rpi"}) / node_memory_MemTotal_bytes{job="node-rpi"}))'
        )
        if rpi_ram:
            metrics['rpi_ram_percent'] = rpi_ram
        
        rpi_temp = self.query_prometheus('node_hwmon_temp_celsius{job="node-rpi"}')
        if rpi_temp:
            metrics['rpi_temp_celsius'] = rpi_temp
        
        # === PC METRICS ===
        pc_power = self.query_prometheus('scaph_host_power_microwatts / 1000000')
        if pc_power:
            metrics['pc_power_watts'] = pc_power
        
        pc_cpu = self.query_prometheus(
            '100 - (avg by (instance) (rate(node_cpu_seconds_total{job="node-pc",mode="idle"}[30s])) * 100)'
        )
        if pc_cpu:
            metrics['pc_cpu_percent'] = pc_cpu
        
        pc_ram = self.query_prometheus(
            '100 * (1 - ((node_memory_MemAvailable_bytes{job="node-pc"} or '
            'node_memory_Buffers_bytes{job="node-pc"} + node_memory_Cached_bytes{job="node-pc"} + '
            'node_memory_MemFree_bytes{job="node-pc"}) / node_memory_MemTotal_bytes{job="node-pc"}))'
        )
        if pc_ram:
            metrics['pc_ram_percent'] = pc_ram

        pc_temp = self.query_prometheus('node_hwmon_temp_celsius{job="node-pc"}')
        if pc_temp:
            metrics['pc_temp_celsius'] = pc_temp

        return metrics
    
    def _collection_loop(self):
        """Collection loop running in separate thread"""
        while self.is_collecting:
            metrics = self.collect_metrics_once()
            self.metrics_data.append(metrics)
            time.sleep(self.sampling_interval)
    
    def start_collection(self):
        """Starts metrics collection in background"""
        if self.is_collecting:
            print("Warning: Collection already in progress")
            return
        
        self.is_collecting = True
        self.start_time = time.time()
        self.metrics_data = []
        
        self.collection_thread = threading.Thread(target=self._collection_loop, daemon=True)
        self.collection_thread.start()
    
    def stop_collection(self):
        """Stops metrics collection"""
        if not self.is_collecting:
            return
        
        self.is_collecting = False
        self.end_time = time.time()
        
        if self.collection_thread:
            self.collection_thread.join(timeout=10)
        
        print(f"Collection stopped. Captured {len(self.metrics_data)} snapshots")
    
    def calculate_statistics(self) -> Dict:
        """Calculates statistics of collected metrics"""
        if not self.metrics_data:
            return {}
        
        stats = {
            'collection_duration_seconds': self.end_time - self.start_time if self.end_time else 0,
            'samples_count': len(self.metrics_data),
            'sampling_interval_seconds': self.sampling_interval,
        }
        
        metric_keys = [k for k in self.metrics_data[0].keys() if k not in ['timestamp', 'datetime']]
        
        for key in metric_keys:
            values = [m[key] for m in self.metrics_data if key in m]
            if values:
                stats[f'{key}_mean'] = sum(values) / len(values)
                stats[f'{key}_max'] = max(values)
                stats[f'{key}_min'] = min(values)
                stats[f'{key}_std'] = self._std_dev(values)
        
        if any('rpi_power_watts' in m for m in self.metrics_data):
            rpi_energy = self._calculate_energy('rpi_power_watts')
            stats['rpi_energy_joules'] = rpi_energy
            stats['rpi_energy_wh'] = rpi_energy / 3600
        
        if any('pc_power_watts' in m for m in self.metrics_data):
            pc_energy = self._calculate_energy('pc_power_watts')
            stats['pc_energy_joules'] = pc_energy
            stats['pc_energy_wh'] = pc_energy / 3600
        
        return stats
    
    def _calculate_energy(self, power_key: str) -> float:
        """Calculates total energy using trapezoidal integration"""
        energy = 0.0
        
        for i in range(len(self.metrics_data) - 1):
            current = self.metrics_data[i]
            next_m = self.metrics_data[i + 1]
            
            if power_key in current and power_key in next_m:
                dt = next_m['timestamp'] - current['timestamp']
                avg_power = (current[power_key] + next_m[power_key]) / 2
                energy += avg_power * dt
        
        return energy
    
    def _std_dev(self, values: List[float]) -> float:
        """Calculates standard deviation"""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5
    
    def get_summary(self) -> Dict:
        """Returns a complete summary of metrics"""
        stats = self.calculate_statistics()
        
        return {
            'start_time': datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None,
            'end_time': datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            'statistics': stats,
            'raw_samples': self.metrics_data
        }
    
    def export_to_json(self, filename: str):
        """Exports data to JSON"""
        summary = self.get_summary()
        with open(filename, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"Metrics exported to: {filename}")
    
    def print_summary(self):
        """Prints a readable summary of metrics"""
        stats = self.calculate_statistics()
        
        if not stats:
            print("No data to display")
            return
        
        print("\n" + "="*70)
        print("ENERGY METRICS SUMMARY")
        print("="*70)
        
        print(f"\nDuration: {stats.get('collection_duration_seconds', 0):.2f}s")
        print(f"Samples: {stats.get('samples_count', 0)} (interval: {stats.get('sampling_interval_seconds', 0)}s)")
        
        if 'rpi_power_watts_mean' in stats:
            print(f"\nRASPBERRY PI:")
            print(f"   Power: {stats['rpi_power_watts_mean']:.3f}W "
                  f"(min: {stats['rpi_power_watts_min']:.3f}W, max: {stats['rpi_power_watts_max']:.3f}W)")
            print(f"   CPU: {stats.get('rpi_cpu_percent_mean', 0):.1f}% "
                  f"(max: {stats.get('rpi_cpu_percent_max', 0):.1f}%)")
            print(f"   RAM: {stats.get('rpi_ram_percent_mean', 0):.1f}% "
                  f"(max: {stats.get('rpi_ram_percent_max', 0):.1f}%)")
            print(f"   Total Energy: {stats.get('rpi_energy_joules', 0):.2f} J "
                  f"({stats.get('rpi_energy_wh', 0):.4f} Wh)")
        
        if 'pc_power_watts_mean' in stats:
            print(f"\nPC:")
            print(f"   Power: {stats['pc_power_watts_mean']:.3f}W "
                f"(min: {stats['pc_power_watts_min']:.3f}W, max: {stats['pc_power_watts_max']:.3f}W)")
            if 'pc_cpu_percent_mean' in stats:
                print(f"   CPU: {stats.get('pc_cpu_percent_mean', 0):.1f}% "
                    f"(max: {stats.get('pc_cpu_percent_max', 0):.1f}%)")
            if 'pc_ram_percent_mean' in stats: 
                print(f"   RAM: {stats.get('pc_ram_percent_mean', 0):.1f}% "
                    f"(max: {stats.get('pc_ram_percent_max', 0):.1f}%)")
            if 'pc_temp_celsius_mean' in stats:
                print(f"   Temperature: {stats.get('pc_temp_celsius_mean', 0):.1f}°C "
                    f"(max: {stats.get('pc_temp_celsius_max', 0):.1f}°C)")
            print(f"   Total Energy: {stats.get('pc_energy_joules', 0):.2f} J "
                f"({stats.get('pc_energy_wh', 0):.4f} Wh)")
        
        print("="*70 + "\n")


if __name__ == "__main__":
    collector = PrometheusMetricsCollector(
        prometheus_url="http://localhost:9090",
        sampling_interval=2
    )
    
    print("Simulating 30-second workflow...")
    
    collector.start_collection()
    time.sleep(30)
    collector.stop_collection()
    
    collector.print_summary()
    collector.export_to_json("energy_metrics.json")