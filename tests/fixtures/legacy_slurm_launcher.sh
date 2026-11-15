#! /bin/bash
export PATH="$HOME/.local/bin:$PATH"
# This is the DagOn launcher script

code=0
echo 
 echo "************************************"
 echo 
# Change the current directory to the working directory
cd /scratch/C
if [ $? -ne 0 ]; then code=1; fi 

# Start staging in



# Create the destination directory
mkdir -p /scratch/C/.dagon/inputs/wf/A//
if [ $? -ne 0 ]; then code=1; fi

# Add the copy command

#! /bin/bash

src=/scratch/A//a.txt
dst=/scratch/C/.dagon/inputs/wf/A//
mode=0
jobs=1
partition=''

job_ids=()

for file in $src
do
cmd="cp -r \"$file\" \"$dst\""
case $mode in
    1)
    # Run in parallel using local queue
    find $src -type f,l | parallel -j$jobs "$cmd"
    break
    ;;
    2)
    # Run in parallel using slurm
    job_id=$(sbatch --job-name=stagein --partition=$partition --ntasks=1 --cpus-per-task=1 --mem=1024 --wrap="$cmd" | awk '{print $4}')
    job_ids+=($job_id)
    ;;
    *)
    # Run requentially
    eval "$cmd"
    ;;
esac
done

# Wait for all sbatch jobs to complete
if [ "${#job_ids[@]}" -gt 0 ]; then
    echo "Waiting for all copies to complete..."
    while true; do
        # Check if any jobs are still in the queue
        pending_jobs=$(squeue -j "${job_ids[*]}" -h -o '%A')
        if [ -z "$pending_jobs" ]; then
            break
        fi
        # Wait a few seconds before checking again
        sleep 5
    done
fi
        
if [ $? -ne 0 ]; then code=1; fi

# Create the destination directory
mkdir -p /scratch/C/.dagon/inputs/wf/B//
if [ $? -ne 0 ]; then code=1; fi

# Add the copy command

#! /bin/bash

src=/scratch/B//b.txt
dst=/scratch/C/.dagon/inputs/wf/B//
mode=0
jobs=1
partition=''

job_ids=()

for file in $src
do
cmd="cp -r \"$file\" \"$dst\""
case $mode in
    1)
    # Run in parallel using local queue
    find $src -type f,l | parallel -j$jobs "$cmd"
    break
    ;;
    2)
    # Run in parallel using slurm
    job_id=$(sbatch --job-name=stagein --partition=$partition --ntasks=1 --cpus-per-task=1 --mem=1024 --wrap="$cmd" | awk '{print $4}')
    job_ids+=($job_id)
    ;;
    *)
    # Run requentially
    eval "$cmd"
    ;;
esac
done

# Wait for all sbatch jobs to complete
if [ "${#job_ids[@]}" -gt 0 ]; then
    echo "Waiting for all copies to complete..."
    while true; do
        # Check if any jobs are still in the queue
        pending_jobs=$(squeue -j "${job_ids[*]}" -h -o '%A')
        if [ -z "$pending_jobs" ]; then
            break
        fi
        # Wait a few seconds before checking again
        sleep 5
    done
fi
        
if [ $? -ne 0 ]; then code=1; fi

# Invoke the command
cat /scratch/C/.dagon/inputs/wf/A//a.txt /scratch/C/.dagon/inputs/wf/B//b.txt > c.txt | tee /scratch/C/.dagon/stdout.txt
(exit "${PIPESTATUS[0]}")
if [ $? -ne 0 ]; then code=1; fi

# Perform post process
exit $code