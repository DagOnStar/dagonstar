from enum import Enum
import os

from dagon.batch import Batch
from dagon.batch import Slurm

from dagon.remote import RemoteTask
from dagon.communication.data_transfer import GlobusManager



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
    DYNOSTORE = 9


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

    def __init__(self, data_mover, stager_mover, cfg):
        self.data_mover = data_mover
        self.stager_mover = stager_mover
        self.cfg = cfg

    def stage_in(self, dst_task, src_task, dst_path, local_path):
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
        # if dynostore is available, use it
        print(src_task_info)
        print(dst_task_info)
        if "dynostore" in src_task.workflow.cfg:
            data_mover = DataMover.DYNOSTORE
        elif dst_task_info is not None and src_task_info is not None:
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

        print(data_mover)

        src = src_task.get_scratch_dir() + "/" + local_path

        dst = dst_path + "/" + os.path.dirname(os.path.abspath(local_path))

        # Check if the symbolic link have to be used...
        if data_mover == DataMover.DYNOSTORE:
            dyno_conf = src_task.workflow.cfg['dynostore']
            dyno_server = f"{dyno_conf.get("host")}:{dyno_conf.get("port")}"
            command = command + "# Add the dynostore command\n"
            command += f"sleep 1\n"
            command += f"dynostore --server {dyno_server} get_catalog {os.path.basename(src_task.get_scratch_dir())} {dst}"
        elif data_mover == DataMover.GRIDFTP:
            # data could be copy using globus sdk
            ep1 = src_task.get_endpoint()
            ep2 = dst_task.get_endpoint()
            gm = GlobusManager(
                ep1, ep2, self.cfg["globus"]["clientid"], self.cfg["globus"]["intermadiate_endpoint"])

            # generate tar with data
            # tar_path = src + "/data.tar"
            # command_tar = "tar -czvf %s %s --exclude=*.tar" % (tar_path, src_task.get_scratch_dir())
            # result = src_task.execute_command(command_tar)

            # get filename from path
            intermediate_filename = os.path.basename(local_path)
            dst = dst_path + "/" + \
                os.path.dirname(os.path.abspath(local_path)) + \
                "/" + intermediate_filename

            # + "/" + "data.tar.gz")
            gm.copy_data(src, dst, intermediate_filename)

        elif data_mover == DataMover.LINK:
            # Add the link command
            command = command + "# Add the link command\n"
            cmd = "ln -sf $file $dst"
            if StagerMover(self.stager_mover) == StagerMover.PARALLEL:
                cmd = "ln -sf {} $dst"
            command = command + \
                self.generate_command(src, dst, cmd, self.stager_mover.value)

        # Check if the copy have to be used...
        elif data_mover == DataMover.COPY:
            # Add the copy command
            command = command + "# Add the copy command\n"
            cmd = "cp -r $file $dst"
            if StagerMover(self.stager_mover) == StagerMover.PARALLEL:
                cmd = "cp -r {} $dst"
            command = command + \
                self.generate_command(src, dst, cmd, self.stager_mover.value)

        # Check if the secure copy have to be used...
        elif data_mover == DataMover.SCP:
            # Add the copy command
            command = command + "# Add the secure copy command\n"
            # if source is accessible from destiny machine
            if isinstance(src_task, RemoteTask):
                # copy my public key
                key = dst_task.get_public_key()
                src_task.add_public_key(key)
                cmd = "scp -r -o LogLevel=ERROR -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i " + dst_task.working_dir + \
                    "/.dagon/ssh_key -r " + src_task.get_user() + "@" + src_task.get_ip() + ":" + \
                    "$file $dst \n\n"
                if StagerMover(self.stager_mover) == StagerMover.PARALLEL:
                    cmd = "scp -r -o LogLevel=ERROR -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i " + dst_task.working_dir + \
                          "/.dagon/ssh_key -r " + src_task.get_user() + "@" + src_task.get_ip() + ":" + \
                        "{} $dst \n\n"
                command = command + \
                    self.generate_command(
                        src, dst, cmd, self.stager_mover.value)
                command += "\nif [ $? -ne 0 ]; then code=1; fi"
                # command += "\n rm " + dst_task.working_dir + "/.dagon/ssh_key"
                print(command)
            else:  # if source is a local machine
                # copy my public key
                key = src_task.get_public_key()
                dst_task.add_public_key(key)

                command_mkdir = "mkdir -p " + dst_path + \
                    "/" + os.path.dirname(local_path) + "\n\n"
                res = dst_task.ssh_connection.execute_command(command_mkdir)

                if res['code']:
                    raise Exception("Couldn't create directory %s" %
                                    dst_path + "/" + os.path.dirname(local_path))

                cmd = "scp -r -o LogLevel=ERROR -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i " + src_task.working_dir + \
                    "/.dagon/ssh_key -r " + src + " " +  \
                    dst_task.get_user() + "@" + dst_task.get_ip() + ":" + dst_path + " \n\n"
                if StagerMover(self.stager_mover) == StagerMover.PARALLEL:
                    cmd = "scp -r -o LogLevel=ERROR -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i " + src_task.working_dir + \
                        "/.dagon/ssh_key -r " + " {} " + \
                        dst_task.get_user() + "@" + dst_task.get_ip() + ":$dst \n\n"
                #command_local = self.generate_command(
                #    src, dst, cmd, self.stager_mover.value)

                #print(command_local)
                print("CMD",cmd)
                res = Batch.execute_command(cmd)
                print(res)

                if res['code']:
                    raise Exception("Couldn't copy data from %s to %s" % (
                        src_task.get_ip(), dst_task.get_ip()))

        command += "\nif [ $? -ne 0 ]; then code=1; fi"

        return command

    def generate_command(self, src, dst, cmd, mode):
        return """
#! /bin/bash

src={}
dst={}
mode={}
jobs={}
partition={}

job_ids=()

for file in $src
do
cmd="{}"
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
    $cmd
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
        """.format(src, dst, mode, self.cfg["batch"]["threads"], self.cfg["slurm"]["partition"], cmd)
