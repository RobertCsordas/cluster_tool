#!/usr/bin/env python3

import sys
import wandb
import glob
import os

if len(sys.argv) != 5:
    print(f"Usage: {sys.argv[0]} <sweep id> <wandb_dir_template> <command> <force>")

path_template = sys.argv[2]
cmd_template = sys.argv[3]
force = sys.argv[4] != "0"

sweep = wandb.Api().sweep(sys.argv[1])
r_to_start = [r for r in sweep.runs if force or r.state=="crashed"]
r_to_start.sort(key=lambda x: x.id)

task_id = int(os.environ['SLURM_ARRAY_TASK_ID']) - 1

print(f"RESUME: task id: {task_id}")
if task_id >= len(r_to_start):
    print(f"Error: Job ID ({task_id}) > num of jobs ({r_to_start})")
    exit(-1)

r = r_to_start[task_id]

savedir = sys.argv[2].replace("${id}", r.id)
savedir = glob.glob(savedir)
if len(savedir) != 1:
    print(f"Warning: Save directory not found for {r.id}. Skipping...")
    exit(-1)

savedir = savedir[0]
flist = [f for f in os.listdir(savedir) if not os.path.isfile(f) and f.lower()]
flist.sort(key=lambda x: os.path.getmtime(os.path.join(savedir, x)))

if len(flist) == 0:
    print(f"Warning: No checkpoint found for {r.id}. Skipping...")
    exit(-1)

ckpt = os.path.join(savedir, flist[-1])
print(f"Run {r.id}: Found checkpoint to resume: {ckpt}")

cmd = cmd_template.replace("${ckpt}", ckpt)
print(f"Running command {cmd}")

os.system(cmd)
