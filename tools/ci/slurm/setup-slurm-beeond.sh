#!/bin/bash
# Configure a single-node Slurm cluster with an emulated BeeOND site on an
# Ubuntu GitHub runner (requires sudo).  CI only: do not use on real systems.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
node=$(hostname -s)
cpus=$(nproc)

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  slurm-wlm munge rsync
sudo systemctl stop slurmd slurmctld 2>/dev/null || true

sudo install -d -o slurm -g slurm /var/lib/slurm/slurmctld /var/lib/slurm/slurmd /var/log/slurm
sudo install -m 0755 "$here/beeond-prolog.sh" /etc/slurm/beeond-prolog.sh
sudo install -m 0755 "$here/beeond-epilog.sh" /etc/slurm/beeond-epilog.sh
sudo touch /var/log/slurm/beeond-ci.log
sudo chmod 0644 /var/log/slurm/beeond-ci.log

sudo tee /etc/slurm/slurm.conf > /dev/null <<CONF
ClusterName=dagonci
SlurmctldHost=${node}(127.0.0.1)
AuthType=auth/munge
MpiDefault=none
ProctrackType=proctrack/linuxproc
TaskPlugin=task/none
JobAcctGatherType=jobacct_gather/none
ReturnToService=2
SlurmUser=slurm
SlurmctldPidFile=/run/slurmctld.pid
SlurmdPidFile=/run/slurmd.pid
SlurmdSpoolDir=/var/lib/slurm/slurmd
StateSaveLocation=/var/lib/slurm/slurmctld
SlurmctldLogFile=/var/log/slurm/slurmctld.log
SlurmdLogFile=/var/log/slurm/slurmd.log
SchedulerType=sched/backfill
SelectType=select/cons_tres
SelectTypeParameters=CR_Core
PrologFlags=Alloc
Prolog=/etc/slurm/beeond-prolog.sh
Epilog=/etc/slurm/beeond-epilog.sh
KillWait=10
InactiveLimit=0
MinJobAge=300
NodeName=${node} NodeAddr=127.0.0.1 CPUs=${cpus} State=UNKNOWN
PartitionName=ci Nodes=${node} Default=YES MaxTime=INFINITE State=UP OverSubscribe=FORCE:4
CONF
sudo chmod 0644 /etc/slurm/slurm.conf

sudo systemctl restart munge
sudo systemctl restart slurmctld
sudo systemctl restart slurmd

for _ in $(seq 1 60); do
  if sinfo -h -N -o '%T' 2>/dev/null | grep -Eq '^(idle|mixed|allocated)'; then
    break
  fi
  sudo scontrol update nodename="$node" state=resume 2>/dev/null || true
  sleep 2
done
sinfo
sinfo -h -N -o '%T' | grep -Eq '^(idle|mixed|allocated)' || {
  sudo tail -n 50 /var/log/slurm/slurmctld.log /var/log/slurm/slurmd.log
  exit 1
}
# Smoke test: a BeeOND job sees its writable mount, an ordinary job does not.
srun --comment=beeond-fs bash -c 'test -w "/mnt/beeond_${SLURM_JOB_USER:-$(id -un)}-jobid_${SLURM_JOB_ID}"'
srun bash -c '! test -e "/mnt/beeond_${SLURM_JOB_USER:-$(id -un)}-jobid_${SLURM_JOB_ID}"'
echo "Slurm with emulated BeeOND is ready on ${node}"
