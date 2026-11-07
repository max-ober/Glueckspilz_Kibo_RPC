# Installation
1. Clone this repository to somewhere on your device
2. Download the KRPC7 Simulator [here](https://jaxa.krpc.jp/download) and unpack it somewhere
3. Create an empty text file called `sync_config.txt` in the root of the cloned project, the same location `watcher.py` is in
4. Add these lines to `sync_config.txt` and change them accordingly
```
# Path to your local Git repo krpc_user folder
SOURCE_DIR=/home/yourname/documents/my_project_repo/krpc_user

# Path to the simulator's mounted workspace krpc_user folder
DEST_DIR=/home/yourname/documents/krpc7th-simulator/users/catkin_ws/src/krpc_user
```

This script will keep the contents of the simulators `krpc_user` folder synchronized to that of the local git repository


5. Launch `watcher.py`
6. Start the simulator by launching `krpc7th-simulator/simulator.sh`

# Documentation
This projects documentation can be found in the [Wiki](https://github.com/max-ober/Glueckspilz_Kibo_RPC/wiki).