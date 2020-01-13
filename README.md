# Installation

## Requirements

 - LXD
 - LVM / BTRFS / ZFS as container storage backend 
 - Python 3.4+
 - Python packages described in *requirements.txt*

## Installation

 1. Configure your pool (we are using LVM) and linux bridge for your containers by running `lxd init`
 2. Create a container, it will be your base container for the LXC pool
 3. Install openssh-server inside the container and configure users
 4. (Optional) Create a snapshot (ready-only snapshot as a base container is better) of your container
 5. Change the *source* field in *config/container.json* to your container name (or snapshot name). Check https://lxd.readthedocs.io/en/latest/instances/ for more informations on LXD instance configuration
 6. Copy *config/container_ssh.json.example* to *config/container_ssh.json* and configure it. This file describe informations used to connect to LXD containers via SSH.
 7. Configure *config/server.json* - It describe SSH Server behaviors
 8. Generate private RSA key and save it as private.pem
 9. Run sshproxy.py

 
## Installation details (Debian 10)
### LXD installation

`$ apt install snapd python3 python3-pip lvm2`  
`$ snap install lxd`  

### LXD initialization
`$ lxd init`  
`$ lxc storage set vgname volume.size 500MB`  

### Base container creation
`$ lxc launch images:debian/buster/amd64 debian-base`  
`$ lxc snapshot debian-base snap`  

`$ lxc exec debian-base /bin/bash`  
`$ apt update && apt install openssh-server -y`  
`$ passwd root`  
`$ adduser debian`  

### 

  
`$ git clone https://github.com/JJCella/lxd_shell_provider`  
`$ cd lxd_shell_provider`  
Configure json files  (see 5-6-7)  
`$ openssl genrsa -out private.pem 2048`
`$ pip3 install -r requirements.txt`  
`$ python3 sshproxy.py`  