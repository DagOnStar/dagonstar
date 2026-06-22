#!/usr/bin/env python3
import subprocess
import time
import re
from prometheus_client import start_http_server, Gauge

power_watts = Gauge(
    "rpi_pmic_power_watts",
    "Total Raspberry Pi power consumption (PMIC)"
)

rail_power = Gauge(
    "rpi_pmic_rail_power_watts",
    "Power consumption per PMIC rail",
    ["rail"]
)

def read_pmic():
    out = subprocess.check_output(
        ["vcgencmd", "pmic_read_adc"],
        text=True
    )

    volts = {}
    amps = {}
    total = 0.0

    for line in out.splitlines():
        m_v = re.match(r"\s*(\S+)_V\s+volt\(\d+\)=([\d.]+)", line)
        m_a = re.match(r"\s*(\S+)_A\s+current\(\d+\)=([\d.]+)", line)

        if m_v:
            volts[m_v.group(1)] = float(m_v.group(2))
        elif m_a:
            amps[m_a.group(1)] = float(m_a.group(2))

    for rail in volts:
        if rail in amps:
            p = volts[rail] * amps[rail]
            rail_power.labels(rail=rail).set(p)
            total += p

    return total


if __name__ == "__main__":
    start_http_server(9101)
    while True:
        try:
            power_watts.set(read_pmic())
        except Exception as e:
            print(e)
        time.sleep(2)
