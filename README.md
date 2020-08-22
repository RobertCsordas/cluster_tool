# Tool for running NN training on simple Linux cluster

## Installation

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
  
  "wandb" : {
    "apikey": "YOUR_API_KEY_FROM_WANDB"
  },

  "envs": {
    "asdf": "LANG=en_US.utf-8"
  }
}
``` 

Some fields:
* ```hosts``` is just a list of machines you want to use. The script will match prefixes against this list when
specifying where to run.
* ```wandb``` Weights & Biases config.
    * ```apikey``` W&B API key that will be passed to all experiment runs
    * ```project``` which project to use
* ```envs``` Machine-specific environment variables added to each executed command
* ```setup``` List of bash commands to execute when running ```ct setup```
* ```gpu_blacklist``` Blacklist specific GPUs on specific machines
* ```commands``` Override specific commands on specific machines

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


### Setting up the cluster

Run ```ct setup``` in your project directory.

This will copy your SSH ID to all of the machines, so you might be asked to enter your password many times.
If you don't yet have an SSH key, it will auto-generate one.

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

### Specifying how many configurations a W&B client can run

Use argument ```-c <number>```

### Synchronization

```
ct -m kratos,v01 copy
```

It will copy your current working directory to all the target machines. It uses ```rsync```, so only the modified files
will be transmitted. This ensures that your code on the target machine is in perfect sync with your local one.

### Gathering

You can copy back output directories from multiple machines (like Synchronization, just the other way around.)

```ct -m kratos,v01 gather output```

This will download and merge content of the ```output``` folder from the listed machines (into the local output folder).

If the name of files might be in conflict (the same name on multiple machines), then you can use argument ```-p``` to
the host name as a prefix to them.

### Running a command
```ct -m kratos,v01 run 'ls -l'```

### Running a command in screen
```ct -m kratos,v01 screen run 'python3 main.py'```

### Debugging

If something doesn't work, try adding argument ```-d```. It will display all bash commands it used to do the specific
task. By running them (or parts of them) manually can help you figure out what is the problem.

For example:
```ct -m kratos,v01 -d wandb agent <run id>```

### Ray support

It also supports Ray, but since Ray is a pain in the ass, see the code and th example config for further information. 
Let's hope nobody will want to use this ever.