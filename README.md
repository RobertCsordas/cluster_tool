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

It is also GPU-aware: it check which GPUs are free on which machine and runs Weights & Biases and Ray clients only on
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
 