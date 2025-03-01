# Tool for running NN training on simple Linux cluster

## TLDR

If you want to start a new W&B project on the cluster quickly, do the following

* Read and do the "Installation" paragraph
* Copy the sample config file from "Configuration" to ```~/.cluster.json```. Modify your host list to match your 
cluster structure.
* Go to the "Getting started" paragraph


## General idea

It uses SSH to run things on multiple machines without any specific cluster management software.

The project should be somewhere within your home folder (could be in a subfolder). The tool synchronizes the files of
the project with all the machines in the cluster and runs specific commands on them.

It is also GPU-aware: it check which GPUs are free on which machine and runs Weights & Biases clients only on
them.

It also supports fast setup of environment on all the machines in parallel.

## Installation

It requires Python 3.6 or newer.

```pip3 -r requirements.txt```

Checkout the repository, and put the ```bin``` folder in your path.

## Usage

### Configuration
You need a config file. It can be called ```cluster.json``` or ```.cluster.json```. 

It should be either in your home directory (global) or your local project directory (local). 
You can also mix the 2: store global settings in the ```~/.cluster.json``` and project-specific settings
in the project directory.

An example global configuration file:
```json
{
  "hosts": [
      "v02.idsia.ch",
      "v03.idsia.ch",
      "v01.idsia.ch",
      "kratos.idsia.ch",
      "minsky.idsia.ch",
      "asdf",
      "skynet.supsi.ch",
      "x01.idsia.ch",
      "x02.idsia.ch",
      "x03.idsia.ch",
      "x04.idsia.ch",
      "x05.idsia.ch",
      "nikola.idsia.ch",
      "venus.idsia.ch"
  ],
  
  "sync": {
    "exclude": [".git*"]
  },
  
  "wandb" : {
    "apikey": "YOUR_API_KEY_FROM_WANDB"
  },

  "envs": {
    "asdf": "LANG=en_US.utf-8"
  },

  "path": ["~/.local/bin"],
  "wandb_ckpt_path": "wandb/*${id}*/files/checkpoint",
  "resume_command": "--restore ${ckpt}",

  "host_config": {
    "x01.idsia.ch": {
      "user": "username",
      "key": "~/.ssh/id_rsa"
    }
  }
}
``` 

Some fields:
* ```hosts``` is just a list of machines you want to use. The script will match prefixes against this list when
specifying where to run.
* ```host_config``` Configuration for individual hosts. Every field is optional.
  * ```hostname``` the full name of the specific host
    * ```user``` Username
    * ```key``` The SSH key to use
* ```wandb``` Weights & Biases config.
    * ```apikey``` W&B API key that will be passed to all experiment runs
    * ```project``` which project to use
    * ```add_name_argumet```, bool, whether to create a new argument, called name, which is the same as the name of the sweep.
* ```envs``` Machine-specific environment variables added to each executed command. Dict of hostnames and the corresponding env.
If you want to use it on all hosts, specify "all".
* ```setup``` List of bash commands to execute when running ```ct setup```
* ```gpu_blacklist``` Blacklist specific GPUs on specific machines
* ```commands``` Override specific commands on specific machines
* ```sync``` File synchronization configuration
    * ```exclude``` List of files to exclude. Default [".git*"]
    * ```use_gitignore``` Whether to ignore files in gitignore when sychronizing. True by default.
    * ```extra``` List of additional files/directories to synchronize.
* ```path``` List of strings. Add extra lines to the path on the host.
* ```paths``` List of paths for individual machines. Overwrites the default ```path```
  * ```hostname``` the target hostname. The argument is a list of strings (the path).
* ```prefix_command``` Prefix to append to every bash command on a specific host
  * ```hostname``` the target hostname. The argument is a string (the command).
* ```bin_dir```: directory where to put the helper scripts. Machine specific. Dict of hostnames and the corresponding directory. By default ```~/.local/bin```
* ```wandb_ckpt_path```: the relative path of wandb checkpoints. It can contain asterisks and a special ${id} string, which will be replaced by the run id when loading the checkpoint. Default: ```wandb/*${id}*/files/checkpoint```
* ```resume_command```: parametrization to run when resuming a checkpoint. The special string ${ckpt} will be replaced by the checkpoint name. Default: ```--restore ${ckpt}```
* ```nosync_if_exists``` detect if used on the target node itself. Disables syncing if the current dir is under ```target_dir``
  ```hostname```: ```path``` - it checks if this path exists to determine if running locally or not.
 
Example local config file
```json
{
  "wandb" : {
    "project": "rnn_generalization_test_release"
  },

  "setup": [
    "pip3 install -U --user cython",
    "pip3 install -U --user tqdm",
    "pip3 install -U --user psutil",
    "pip3 install -U --user matplotlib",
    "pip3 install -U --user tensorboard",
    "pip3 install -U --user future",
    "pip3 install -U --user filelock",
    "pip3 install -U --user setproctitle",
    "pip3 install -U --user wandb",
    "pip3 install -U --user dataclasses",
    "pip3 install -U --user pillow",
    "pip3 install -U --user torchvision"
  ]
}
```

#### Using W&B entities

If you have your own account but also part of an organization, you might want to specify in which one to run the sweeps. In that case, just add your entity (username or organization name) in front of wandb.project in your config:

```
"wandb" : {
    "project": "csordas/rnn_generalization_test_release"
  },
```

You can always overwrite the project temporarily using the ```-p``` or ```--project``` argument.

#### Blacklisting a GPU

Example: add to you config
```
"gpu_blacklist": {
    "kratos.idsia.ch": [0,1],
    "v01.idsia.ch": [2]
}
```

#### Overriding individual commands on individual hosts

All commands are checked before it's execution against the command override list. This enables you to use the same
commands on the different machines even when they need to be mapped to different things.

Example: add to your config

```
"commands": {
    "asdf": {
        "pip3": "~/.local/bin/pip3.6",
        "python3": "python3.6"
    },

    "kratos": {
        "pip": "pip3",
        "python": "python3"
    }
}
```

### Specifying where to run

All commands can have a target machine, specified by argument ```-m```. It receives a list of machines, with optional
GPU specification (used just for training). To run a command on multiple machines, look at the following example:

```bash
ct -m kratos,v01 run ls
```

If argument ```-m``` is not used, all machines will be used.

#### Which GPU to use

By default the scripts autodetect free GPUs on the target machines.

Specifying GPU can overriden on per-machine basis:
```bash
ct -m 'kratos{0;1;2},v01{0-2}' run ls
```

It can use either a list of GPUs, separated by ```;``` or a range of them, specified by ```-```

#### Allowing to run on already used GPUs

Normally the script doesn't allow to run on GPUs that already have jobs running. However in certain situations some
jobs might be small enough such that one wants to run multiple jobs on a GPU which is already used by some other
process. This can be enforced by adding the ```-FGPU``` flag.

For example:
```bash
ct -m kratos -FGPU wandb sweep task.yaml
```


### Setting up the cluster

Run ```ct setup``` in your project directory.

This will copy your SSH ID to all of the machines, so you might be asked to enter your password many times.
If you don't yet have an SSH key, it will auto-generate one.

### Creating a new Weights & Biases sweep
Example:
```
ct -m kratos wandb sweep sweeps/test.yaml
```

Optionally you can also specify custom sweep name:

```
ct -m kratos wandb sweep CoolSweep sweeps/test.yaml
```

In case the name is not specified, it will use the name of the ```yaml``` file instead (in the example above it 
will be 'test')

It will automatically synchronize your files with the target machines (see Synchronization below).

#### Example W&B YAML

A bit off topic, but here you go, for faster setup

```yaml
program: main.py
command:
  - ${env}
  - python3
  - ${program}
  - ${args}
method: grid
metric:
  name: validation/mean_accuracy
  goal: maximize
parameters:
  log:
    value: wandb
  profile:
    distribution: categorical
    values:
      - trafo_scan
      - scan
  scan.train_split:
    distribution: categorical
    values:
      - length
      - jump
      - turn_left
  analysis.enable:
    value: 0
  stop_after:
    value: 25000
  mask_loss_weight:
    value: 3e-5
  mask_lr:
    value: 1e-2
  sweep_id_for_grid_search:
    distribution: categorical
    values:
      - 1
      - 2
      - 3
      - 4
      - 5
      - 6
      - 7
      - 8
      - 9
      - 10
```

### Attaching new agents to an existing sweep

```
ct -m kratos wandb agent <sweep id>
```

You can copy the command from W&B dashboard and prepend ```ct``` to it.

It will automatically synchronize your files with the target machines (see Synchronization below).

### Running multiple sweeps/agents on the same GPU

Append ```-pg <number>``` to your starting command (```-pg``` = per gpu). For example:

```
ct -m kratos -pg 2 wandb sweep sweeps/test.yaml
```

### Running a sweep on multiple GPUs - or multiple nodes

Use multiple GPUs on a single machine or cluster.

Append ```-mgpu <number>``` to your starting command. For example:

```
ct -m kratos -mgpu 2 wandb sweep sweeps/test.yaml
```

The jobs are started as follows:
- On the head node/master gpu (rank 0), wandb agent is called
- On the rest of the nodes/gpus, the program is called without any arguments. What command is called is extracted from the
  W&B sweep config, by ignoring the environment variable and arguments. Its the responsibility of the training script
  to synchronize information between the head node and the rest of the workers.
- In case of non-slurm run, env variables similar to torchrun are set. Thus, code that work with torchrun should work by default with this script.

### Running multiple Weights & Biases agents


Use multiple parallel agents. It allocates free GPUs for all of them and run this many in parallel.

Append ```-n_runs <number>``` or ```-r <number>``` to your starting command. For example: If you do not specify this,
the number of runs will be automatically set to cover all variants yaml file.

```
ct -m kratos -r 4 wandb sweep sweeps/test.yaml
```

### Resuming Weights & Biases sweep

So far this works only with SLURM.

```
ct -s -m daint wandb resume idsia/lm/3fp2dk2a -mgpu 32
```

It will resume all the crashed experiments. If you want to resume all, even when flagged "finished", add argument ```-f```.

### Specifying how many configurations a W&B client can run

Use argument ```-c <number>```

For example if you want to run 10 trainings with 4 parallel agents each of them running on 2 GPUs 
(which means 2 different nodes on daint):

```
ct -s -m daint -r 4 -c 10 -mgpu 2 wandb sweep sweeps/test.yaml
```

It will use 8 gpus in parallel.

### Cleaning up Weights & Biases files

Weights & Biases stores all files both locally, and uploaded to the remote server. The local files can take up a lot of
space. You can easily clear the files by the following command:

```ct -m kratos wandb cleanup```

_Note_: This command is safe to run even while sweeps are running on the target machine. It will check for the running
sweeps and will not remove their folders in the W&B cache.

By default, the command assumes that W&B directory is relative to the current dir, named ```wandb```. You can specify
alternative paths with an extra argument:

```ct -m kratos wandb cleanup ~/wandb```

### Trying to fix W&B crashed runs

Weights & Biases runs sometime show "crashed" status. If you check the log, there is no errors, it just stops at some
point. This is due to an internal crash to the syncharonizaton mechansim inside the W&B agent. It can also happen if the
iternet stops working for a while. In this case all the logs are stored in a local directory and they can be
synchronized with the server. Run

```ct wandb sync_crashed```

to attempt to fix them. In my experience it works 99% of the time.

It is also possible to specify which sweep you want to synchronize by

```ct wandb sync_crashed <sweep id or name>```

where ```<sweep id or name>``` can be either the sweep id (the 8 random characters identifying the sweep), or the user
readable name shown in the list of sweeps.

### Synchronization with the local machine

```
ct -m kratos,v01 copy
```

It will copy your current working directory to all the target machines. It uses ```rsync```, so only the modified files
will be transmitted. This ensures that your code on the target machine is in perfect sync with your local one.

#### Synchronizing additional files

You might store some files outside of the project directory. You can add them explicitly to the sychronization list,
by adding to your config:

```json
"sync" : {
  "extra": ["~/pretrained"]
},
```

### Gathering

You can copy back output directories from multiple machines (like Synchronization, just the other way around.)

```ct -m kratos,v01 gather output```

This will download and merge content of the ```output``` folder from the listed machines (into the local output folder).

If the name of files might be in conflict (the same name on multiple machines), then you can use argument ```-pf``` to
the host name as a prefix to them.

### Running a command
```ct -m kratos,v01 run 'ls -l'```

### Running a command as root
```ct -m kratos,v01 sudo whoami```

### Running a command in screen
```ct -m kratos,v01 screen run 'python3 main.py'```

### Listing PGIDs of phantom processes

Sometimes processes can get stuck on the GPUs and using memory. In these cases ```nvidia-smi``` doesn't show them, but
```nvidia-smi --query-compute-apps=pid,name --format=csv``` does. But the PIDs are invalid. It turns out that these
processes usually don't have parent processes, which can be used to detect them. You can list the PGIDs of these
processes by ```ct list_phantom```. You can also use it in conjunction with ```-m```. 

For example: ```ct -m kratos list_phantom```

### Killing phantom processes

See section on "Listing PGIDs of phantom processes" for more details on what phantom processes are.

```ct -m kratos kill_phantom```

Note: Killing other user's processes requires sudo.

### Debugging

If something doesn't work, try adding argument ```-d```. It will display all bash commands it used to do the specific
task. By running them (or parts of them) manually can help you figure out what is the problem.

For example:
```ct -m kratos,v01 -d wandb agent <run id>```

### SLURM support

Commands supported on SLURM clusters works exactly like the locals, except that ```-s```/```--slurm``` switch should be
passed such that no command is run accidentally on the cluster. Currently supported commands are ```copy```, 
```wandb sweep``` and ```wandb agent```. Expected duration could also be passed to wandb commands in the form of ```-t hh:mm:ss```
(detaults to 23:59:00).

For example to run each configuration in a sweep on a node run:
```bash
ct -s -m daint wandb sweep sweep.yaml
```

For example to run a sweep on 20 nodes for 10 hours:
```bash
ct -s -m daint wandb sweep sweep.yaml -r 20 -t 10:00:00
```

In order for SLURM to work, it needs additional entries in the ```cluster.json```. The SLURM head node should *not* be
listed under the "hosts" array, but under a separate "slurm" dict. For example:

```json
"slurm": {
  "daint": {
    "target_dir": "$SCRATCH",
    "modules": ["daint-gpu", "PyExtensions", "PyTorch"],
    "account": "your_account",
    "cscs_auth": {
      "username": "<username>",
      "password": "<password>",
      "otp_secret": "<otp secret>"
    }
  }
}
```

Alternative example, with multiple machines with different GPU types:
```
"slurm": {
  "sc": {
    "template": "stanford",
    "target_dir": "/some/common/path/slurm",
    "machines":[
      "bigmachine",
      "smallmachine"
    ],

    "default_partition": "standard",
    "default_cpus_per_gpu": 8,
    "default_mem_per_gpu": 16,

    "partition_map": {
      "standard": "small,big-standard",
      "high": "small-hi,big-hi"
    },
    
    "gpu_map":{
      "titanxp": ["smallmachine"],
      "a100": ["bigmachine"]
    }
  }
},
```
Here, ```headnode``` is the hostname for the node which is used to SLURM the slurm commands, and ```bigmachine``` and ```smallmachine``` are the names of individual machines in SLURM.

Obligatory arguments (separately for each target):
  * ```target_dir```: the local directory to use instead of /home/username. Can contain *remote* environment variables.
  * ```modules```: which modules to load

Optional arguments:
  * ```template```: ```cscs``` or ```stanford```. Use ```cscs``` if you have a big, homogenous machine with 1 GPU per node. Use ```stanford``` otherwise. (The default is cscs for compatiblity reasons).
  * ```account```: under which accunt to schedule the runs. Run ```accounting``` remotely if you don't know what's your account.
  * ```out_dir```: directory where to save output logs. Relative to ```target_dir```. By default ```out```
  * ```cscs_auth```: data for CSCS authentication that requires refreshing the SSH keys every day. You can obtain the secret from the QR code displayed when registering the 2FA, or you can figure it out from a Google Authenticator backup.
  * ```slurm_flags```: extra SLURM flags to provide to sbatch. For example: "slurm_flags": "--mem-per-cpu=16G". Default: "--constraint=gpu --switches=1" for cscs template. To remove, specify empty string.
  * ```default_partition```: The default partition to use
  * ```partition_map```: Optional map between human-readable and real partition names
    * ```human readable name```: ```real name```
  * ```machines```: list of strings, the short hostname of all machines available. The ```-m``` argument will recognize these machines and will allow to run on them directly.
  * ```gpu_map```: Dict of GPU name (arbitrary string) and list of machines (short hostnames). If present, ```machines``` must be defined as well.
  * ```default_cpus_per_gpu```: How many cpus to use per GPU
  * ```default_mem_per_gpu```: How many Gb of memory to use per GPU

### Accessing SLURM behind a front-end server

If you can't directly access the SLURM server, but it is behind another front-end server, you can add a similar entry to
your local ```~/.ssh/config```:

```
Host ela
   Hostname ela.cscs.ch
   User <username>
   IdentityFile ~/.ssh/id_rsa_cscs
Host daint
   Hostname daint.cscs.ch
   User <username>
   IdentityFile ~/.ssh/id_rsa_cscs
   ProxyJump ela
```

Here the ```ProxyJump``` line makes all connections going to ```daint``` go through ```ela```.

Note that in this case you should *not* add the full url the ```config.json```, but the name used after ```Host``` in
the ```~/.ssh/config``` file (in this case just ```daint```).

# Getting started

It's recommended to use W&B for our server experiments. For that, you will need to set up clustertool with your
W&B API key. Go to https://app.wandb.ai/settings, scroll to "API keys", click "New key" and copy your key in the config
file. I recommend to put it in your global config file (```~/.cluster.json```), but it also works locally.

Create a local config file in your project folder, called ```cluster.json```, as follows:
```json
{
  "wandb" : {
    "project": "lr_tuning_test"
  }
}
```

Now you should setup your cluster:

```ct setup```

You have to do this only once, or when python version on the hosts are updated, or the ```setup``` section of the 
config file is changed.


In your training script, you want to log things to W&B. Import 'wandb' and initialize it as follows:

```wandb.init()```

Log your loss with ```wandb.log({"loss": loss})``` periodically.
Finally call ```wandb.join()``` when your training terminates.

To tune for example the learning rate, use argument parser, and create a new argument "lr". Parse and use this learning
rate in your optimizer:

```python
import argparse
args = argparse.ArgumentParser()
args.add_argument("-lr", "--lr", type=float)

opt = args.parse_args()
```
...
```python
optim = torch.optim.Adam(model.parameters(), lr=opt.lr)
```

Start a W&B sweep as follows. First create a yaml config file:

```yaml
program: main.py
command:
  - ${env}
  - python3
  - ${program}
  - ${args}
method: bayes
metric:
  name: loss
  goal: minimize
parameters:
  lr:
    min: 0.001
    max: 0.1
```

Save it as ```lr_tuning.yaml```.

Next run 100 iterations of the training:

```ct -m kratos,v01 -c 100 wandb sweep lr_tuning.yaml``` 

Go to https://app.wandb.ai/, open your sweeps, and you should see your runs there.

## Stopping your runs

Go to W&B sweeps page. If you don't need the data, delete the sweep. It will stop all agents immediately.

If you need your data, go to the sweep, go to the sweep config on the left side menu, and cancel the sweep.

If it still doesn't stop, you can always use ```ct run 'killall -9 wandb'``` followed by 
```ct run 'killall -9 python3'``` which will terminate the runs for sure. (Note: the order is important, otherwise W&B 
will start new runs immediately).
 

 ## Using it with conda

 Add your conda bin path to either ```path``` or ```paths```.