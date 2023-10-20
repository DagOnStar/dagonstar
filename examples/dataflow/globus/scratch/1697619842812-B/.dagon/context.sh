#! /bin/bash
# This is the DagOn launcher script

code=0
cd ./scratch/1697619842812-B/.dagon
#! /bin/bash
# This is the DagOn launcher script

code=0

# Initialize
machine_type="none"
public_id="none"
user="none"
status_sshd="none"
status_ftpd="none"
status_skycds="none"

#get http communication protocol
curl_or_wget=$(if hash curl 2>/dev/null; then echo "curl"; elif hash wget 2>/dev/null; then echo "wget"; fi);


if [ $curl_or_wget = "wget" ]; then
  public_ip=`wget -q -O- https://ipinfo.io/ip`
else
  public_ip=`curl -s https://ipinfo.io/ip`
fi

if [ "$public_ip" == "" ]
then
  # The machine is a cluster frontend (or a single machine)
  machine_type="cluster-frontend"
  public_ip=`ifconfig 2>/dev/null| grep "inet "| grep -v "127.0.0.1"| awk '{print $2}'|grep -v "192.168."|grep -v "172.16."|grep -v "10."|head -n 1`
fi

if [ "$public_ip" == "" ]
then
  # If no public ip is available, then it is a cluster node
  machine_type="cluster-node"
  public_ip=`ifconfig 2>/dev/null| grep "inet "| grep -v "127.0.0.1"| awk '{print $2}'|head -n 1`
fi


# Check if the secure copy is available
status_sshd=`systemctl status sshd 2>/dev/null | grep 'Active' | awk '{print $2}'`
if [ "$status_sshd" == "" ]
then
  status_sshd="none"
fi

# Check if the ftp is available
status_ftpd=`systemctl status globus-gridftp-server 2>/dev/null|grep "Active"| awk '{print $2}'`
if [ "$status_ftpd" == "" ]
then
  status_ftpd="none"
fi

# Check if the grid ftp is available
status_gsiftpd=`systemctl status globus-gridftp-server 2>/dev/null|grep "Active"| awk '{print $2}'`
if [ "$status_gsiftpd" == "" ]
then
  status_gsiftpd="none"
fi

#check if skycds container is running
status_docker=`systemctl status docker 2>/dev/null|grep "Active"| awk '{print $2}'`
if [ "$status_gsiftpd" == "active" ]
then
    if [ "$(docker ps -aq -f status=running -f name=client)" ]; then
    # cleanup
        status_skycds="active"
    fi
fi

# Get the user
user=$USER

echo "no" | ssh-keygen  -b 2048 -t rsa -f ssh_key -q -N ""  >/dev/null

# Construct the json
json="{\"type\":\"$machine_type\",\"ip\":\"$public_ip\",\"user\":\"$user\",\"SCP\":\"$status_sshd\",\"FTP\":\"$status_ftpd\",\"GRIDFTP\":\"$status_gsiftpd\",\"SKYCDS\":\"$status_skycds\"}"
echo $json

