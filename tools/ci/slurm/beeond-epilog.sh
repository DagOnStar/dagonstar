#!/bin/bash
# Slurm Epilog that emulates BeeOND teardown for CI: the job volume is
# destroyed when the job ends, so only data persisted before then survives.
mount="/mnt/beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}"
if [ -d "$mount" ]; then
  rm -rf -- "$mount"
  echo "destroy $SLURM_JOB_ID $mount" >> /var/log/slurm/beeond-ci.log
fi
exit 0
