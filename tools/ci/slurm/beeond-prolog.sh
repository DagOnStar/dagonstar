#!/bin/bash
# Slurm Prolog that emulates a BeeOND site for CI (runs as root on the node).
# Jobs whose comment contains "beeond-fs" get a private, job-owned directory at
# the site mount point, like BeeGFS On Demand; other jobs get nothing.
comment="${SLURM_JOB_COMMENT:-}"
if [ -z "$comment" ]; then
  comment=$(scontrol show job "$SLURM_JOB_ID" -o 2>/dev/null | sed -n 's/.* Comment=\([^ ]*\).*/\1/p')
fi
case ",$comment," in
  *beeond-fs*) ;;
  *) exit 0 ;;
esac
mount="/mnt/beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}"
mkdir -p "$mount" || exit 1
chown "${SLURM_JOB_UID}:${SLURM_JOB_GID}" "$mount" || exit 1
chmod 700 "$mount"
echo "create $SLURM_JOB_ID $mount" >> /var/log/slurm/beeond-ci.log
exit 0
