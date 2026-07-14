from enum import Enum
import os
import logging
from typing import Dict, Any

from dagon.batch import Batch
from dagon.batch import Slurm

from dagon.remote import RemoteTask
from dagon.communication.data_transfer import GlobusManager
from dagon.shell import quote, remote_target


class DataMover(Enum):
    """
    Possible transfer protocols/apps

    :cvar DONTMOVE: Don't move nothing
    :cvar LINK: Using a symbolic link
    :cvar COPY: Copying the data
    :cvar SCP: Using secure copy
    :cvar HTTP: Using HTTP
    :cvar HTTPS: Using HTTPS
    :cvar FTP: Using FTP
    :cvar SFTP: Using secure FTP
    :cvar GRIDFTP: Using Globus GridFTP
    """

    DONTMOVE = 0
    LINK = 1
    COPY = 2
    SCP = 3
    HTTP = 4
    HTTPS = 5
    FTP = 6
    SFTP = 7
    GRIDFTP = 8
    SKYCDS = 9
    DYNOSTORE = 10


class StagerMover(Enum):
    """
    Possible mode

    :cvar NORMAL: sequential
    :cvar PARALLEL: using threads
    :cvar SLURM: using Slurm
    """
    NORMAL = 0
    PARALLEL = 1
    SLURM = 2


class ProtocolStatus(Enum):
    """
    Status of the protocol on a machine

    :cvar ACTIVE: Protocol running and active
    :cvar NONE: Protocol not installed
    :cvar INACTIVE: Protocol not running
    """

    ACTIVE = "active"
    NONE = "none"
    INACTIVE = "inactive"


class Stager(object):
    """
    Choose the transference protocol to move data between tasks
    """

    def __init__(self, data_mover: DataMover, stager_mover: StagerMover, cfg: Dict[str, Dict[str, str]]):
        self.data_mover = data_mover
        self.stager_mover = stager_mover
        self.cfg = cfg
        self.logger = logging.getLogger()

    def stage_in(self, dst_task: Any, src_task: Any, dst_path: str, local_path: str) -> str:
        """
        Evaluates the context of the machines and choose the transfer protocol

        :param dst_task: task where the data has to be put
        :type dst_task: :class:`dagon.task.Task`

        :param src_task: task from the data has to be taken
        :type src_task: :class:`dagon.task.Task`

        :param dst_path: path where the file is going to be save on the destiny directory
        :type dst_path: str

        :param local_path: path where is the file to be transferred on the source task
        :type local_path: str

        :return: comand to move the data
        :rtype: str with the command
        """

        data_mover = DataMover.DONTMOVE
        command = ""

        # ToDo: this have to be make automatic
        # get tasks info and select transference protocol
        dst_task_info = dst_task.get_info()
        src_task_info = src_task.get_info()
        
        # check transference protocols and remote machine info if is available
        if dst_task_info is not None and src_task_info is not None:
            if dst_task_info['ip'] == src_task_info['ip']:
                data_mover = self.data_mover
            else:
                protocols = ["GRIDFTP", "SCP", "FTP"]
                for p in protocols:
                    if ProtocolStatus(src_task_info[p]) is ProtocolStatus.ACTIVE:
                        data_mover = DataMover[p]

                        if data_mover == DataMover.GRIDFTP and \
                                not dst_task.get_endpoint() and \
                                not src_task.get_endpoint():
                            continue

                        break
        else:  # best effort (SCP)
            data_mover = self.data_mover


        src = src_task.get_scratch_dir() + "/" + local_path

        dst = dst_path + "/" + os.path.dirname(os.path.abspath(local_path))
        
        # Check if the symbolic link have to be used...
        if data_mover == DataMover.GRIDFTP:
            from dagon.communication.data_transfer import GlobusManager

            # data could be copy using globus sdk
            ep1 = src_task.get_endpoint()
            ep2 = dst_task.get_endpoint()
            gm = GlobusManager(ep1, ep2, self.cfg["globus"]["clientid"], self.cfg["globus"]["intermadiate_endpoint"])

            # generate tar with data
            #tar_path = src + "/data.tar"
            #command_tar = "tar -czvf %s %s --exclude=*.tar" % (tar_path, src_task.get_scratch_dir())
            #result = src_task.execute_command(command_tar)

            #get filename from path 
            intermediate_filename = os.path.basename(local_path)
            dst = dst_path + "/" + os.path.dirname(os.path.abspath(local_path)) + "/" + intermediate_filename

            gm.copy_data(src, dst, intermediate_filename)# + "/" + "data.tar.gz")

        elif data_mover == DataMover.SKYCDS:
            from dagon.communication.data_transfer import SKYCDS

            skycds = SKYCDS()
            upload_result = skycds.upload_data(src_task, src_task.get_scratch_dir(), encryption=True)
            download_result = skycds.download_data(dst_task, dst_path)


        elif data_mover == DataMover.LINK:
            # Add the link command
            command = command + "# Add the link command\n"
            cmd = "ln -sf \"$file\" \"$dst\""
            if StagerMover(self.stager_mover) == StagerMover.PARALLEL:
                cmd = "ln -sf {} \"$dst\""
            command = command + self.generate_command(src, dst, cmd, self.stager_mover.value)

        # Check if the copy have to be used...
        elif data_mover == DataMover.COPY:
            # Add the copy command
            command = command + "# Add the copy command\n"
            cmd = "cp -r \"$file\" \"$dst\""
            if StagerMover(self.stager_mover) == StagerMover.PARALLEL:
                cmd = "cp -r {} \"$dst\""
            command = command + self.generate_command(src, dst, cmd, self.stager_mover.value)

        # Check if the secure copy have to be used...
        elif data_mover == DataMover.SCP:
            # Add the copy command
            command = command + "# Add the secure copy command\n"
            if isinstance(src_task, RemoteTask):  # if source is accessible from destiny machine
                # copy my public key
                key = dst_task.get_public_key()
                src_task.add_public_key(key)
                key_path = dst_task.working_dir + "/.dagon/ssh_key"
                source = remote_target(src_task.get_user(), src_task.get_ip(), '"$file"')
                cmd = ("scp -r -o LogLevel=ERROR -o StrictHostKeyChecking=no "
                       "-o UserKnownHostsFile=/dev/null -i " + quote(key_path) +
                       " -r " + source + ' "$dst"\n\n')
                if StagerMover(self.stager_mover) == StagerMover.PARALLEL:
                    source = remote_target(src_task.get_user(), src_task.get_ip(), "{}")
                    cmd = ("scp -r -o LogLevel=ERROR -o StrictHostKeyChecking=no "
                           "-o UserKnownHostsFile=/dev/null -i " + quote(key_path) +
                           " -r " + source + ' "$dst"\n\n')
                command = command + self.generate_command(src, dst, cmd, self.stager_mover.value)
                command += "\nif [ $? -ne 0 ]; then code=1; fi"
                # command += "\n rm " + dst_task.working_dir + "/.dagon/ssh_key"
            else:  # if source is a local machine
                # copy my public key
                key = src_task.get_public_key()
                dst_task.add_public_key(key)

                command_mkdir = "mkdir -p " + quote(dst_path + "/" + os.path.dirname(local_path)) + "\n\n"
                res = dst_task.ssh_connection.execute_command(command_mkdir)

                if res['code']:
                    raise Exception("Couldn't create directory %s" % dst_path + "/" + os.path.dirname(local_path))

                key_path = src_task.working_dir + "/.dagon/ssh_key"
                destination = remote_target(dst_task.get_user(), dst_task.get_ip(), '"$dst"')
                cmd = ("scp -r -o LogLevel=ERROR -o StrictHostKeyChecking=no "
                       "-o UserKnownHostsFile=/dev/null -i " + quote(key_path) +
                       ' -r "$file" ' + destination + "\n\n")
                if StagerMover(self.stager_mover) == StagerMover.PARALLEL:
                    destination = remote_target(dst_task.get_user(), dst_task.get_ip(), '"$dst"')
                    cmd = ("scp -r -o LogLevel=ERROR -o StrictHostKeyChecking=no "
                           "-o UserKnownHostsFile=/dev/null -i " + quote(key_path) +
                           " -r {} " + destination + "\n\n")
                command_local = self.generate_command(src, dst, cmd, self.stager_mover.value)
                res = Batch.execute_command(command_local)

                if res['code']:
                    raise Exception("Couldn't copy data from %s to %s" % (src_task.get_ip(), dst_task.get_ip()))

        command += "\nif [ $? -ne 0 ]; then code=1; fi"

        return command

    def generate_command(self, src: str, dst: str, cmd: str, mode: int) -> str:
        batch_cfg = self.cfg.get("batch", {})
        slurm_cfg = self.cfg.get("slurm", {})
        jobs = batch_cfg.get("threads", "1")
        partition = slurm_cfg.get("partition", "")
        return """
#! /bin/bash

src={src}
dst={dst}
mode={mode}
jobs={jobs}
partition={partition}

job_ids=()

for file in $src
do
cmd="{cmd}"
case $mode in
    1)
    # Run in parallel using local queue
    find $src -type f,l | parallel -j$jobs "$cmd"
    break
    ;;
    2)
    # Run in parallel using slurm
    job_id=$(sbatch --job-name=stagein --partition=$partition --ntasks=1 --cpus-per-task=1 --mem=1024 --wrap="$cmd" | awk '{{print $4}}')
    job_ids+=($job_id)
    ;;
    *)
    # Run requentially
    eval "$cmd"
    ;;
esac
done

# Wait for all sbatch jobs to complete
if [ "${{#job_ids[@]}}" -gt 0 ]; then
    echo "Waiting for all copies to complete..."
    while true; do
        # Check if any jobs are still in the queue
        pending_jobs=$(squeue -j "${{job_ids[*]}}" -h -o '%A')
        if [ -z "$pending_jobs" ]; then
            break
        fi
        # Wait a few seconds before checking again
        sleep 5
    done
fi
        """.format(
            src=quote(src),
            dst=quote(dst),
            mode=int(mode),
            jobs=quote(jobs),
            partition=quote(partition),
            cmd=cmd.replace('"', '\\"'),
        )