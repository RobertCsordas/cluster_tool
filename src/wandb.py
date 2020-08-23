from typing import Optional, Tuple
from .detect_gpus import get_top_gpus
from .config import config
from .utils import get_relative_path
from .process_tools import remote_run, run_process
from .parallel_map import parallel_map
from .sync import copy_local_dir
import math
import socket
import tempfile
import os
import wandb

def get_wandb_env() -> str:
    wandb = config.get("wandb", {}).get("apikey")
    if wandb is None:
        wandb = ""
    else:
        wandb = " WANDB_API_KEY=" + wandb + " "
    return wandb


def run_agent(sweep_id: str, count: Optional[int], n_gpus: Optional[int], agents_per_gpu: Optional[int]):
    agents_per_gpu = agents_per_gpu or 1
    relpath = get_relative_path()

    copy_local_dir(config["hosts"])

    gpu_for_count = int(math.ceil(count / agents_per_gpu)) if count else None
    use_gpus = get_top_gpus(gpu_for_count if n_gpus is None else (n_gpus if count is None else
                                                                  min(gpu_for_count, n_gpus)))

    wandb_key = get_wandb_env()
    assert wandb_key, "W&B API key is needed for staring a W&B swype"

    all_gpus = sum([[(h, gpu) for gpu in g] for h, g in use_gpus.items()], []) * agents_per_gpu
    count = f"--count {int(math.ceil(count / len(all_gpus)))}" if count else ""

    def start_wandb_client(arg: Tuple[str, int]):
        host, gpu = arg

        cd = config.get_command(host, "cd")
        screen = config.get_command(host, "screen")
        wandb = config.get_command(host, "wandb", "~/.local/bin/wandb")

        cmd = f"{cd} {relpath}; CUDA_VISIBLE_DEVICES={gpu} {wandb_key}  {screen} -d -S "+\
              f"wandb_sweep_{sweep_id.split('/')[-1]}_gpu_{gpu} -m " + \
              f"{wandb} agent {sweep_id} {count}"

        _, errcode = remote_run(host, cmd + " 2>/dev/null")

        if errcode != 0:
            print("Failed to start W&B client on %s (command: %s)" % (host, cmd))

    parallel_map(all_gpus, start_wandb_client)


def sweep(name: str, config_file: str, count: Optional[int], n_gpus: Optional[int],
          agents_per_gpu: Optional[int]):
    localhost = socket.gethostname()
    wandb = config.get_command(localhost, "wandb", "~/.local/bin/wandb")

    project = config.get("wandb", {}).get("project")
    assert project is not None, "wandb/project must be specified in order to be able to start sweeps"

    with open(config_file, "r") as f:
        config_data = f.read()

    config_data += "\n"
    config_data += "  name:\n"
    config_data += f"   value: sweep_{name}\n"

    file, tmpname = tempfile.mkstemp(".yaml", text=True)
    os.close(file)
    try:
        with open(tmpname, "w") as f:
            f.write(config_data)
            f.close()

        stdout, stderr, err = run_process(f"{wandb} sweep --project {project} --name {name} {tmpname}", get_stderr=True)
    finally:
        os.remove(tmpname)

    if err!=0:
        assert False, "Failed to create sweep. Output: \n"+stdout+stderr

    sweep_id = stderr.split(" ")[-1].strip()
    print(f"Created sweep with ID: {sweep_id}")

    run_agent(sweep_id, count, n_gpus, agents_per_gpu)


def find_entity() -> str:
    # UGLY HACK, don't know why it works. It's based on reverse-engineering wandb cli client
    wandb.wandb_controller._get_sweep_url(wandb.InternalApi(), "")
    return wandb.env.get_entity()


def cleanup(wandb_relative_path: str):
    wandb_relative_path = get_relative_path(wandb_relative_path)
    running_sweeps_per_host = {}

    def get_running_sweeps(host: str):
        out, err = remote_run(host, "screen -ls")
        running_sweeps = set()
        if err == 0:
            sw = [o.strip() for o in out.split("\n") if o][1:-1]
            for s in sw:
                if ".wandb_sweep_" not in s:
                    continue

                running_sweeps.add(s.split("_")[2])

        running_sweeps_per_host[host] = running_sweeps

    parallel_map(config["hosts"], get_running_sweeps)
    all_sweeps = set().union(*running_sweeps_per_host.values())

    runs_per_sweep = {}
    project = config.get("wandb", {}).get("project")
    entity = find_entity()

    api = wandb.Api()
    for sw in all_sweeps:
        runs_per_sweep[sw] = set(r.id for r in api.runs(f"{entity}/{project}", {"sweep": sw}))

    def do_cleanup(host: str):
        my_runs = set().union(*(runs_per_sweep[s] for s in running_sweeps_per_host[host]))
        dirs, errcode = remote_run(host, f"ls {wandb_relative_path}")
        if errcode!=0:
            return
        dirs = [d.strip() for d in dirs.split("\n")]
        dirs = [d for d in dirs if d and d.split("-")[-1] not in my_runs]
        for d in dirs:
            d = f"{wandb_relative_path}/'{d}'"
            out, errcode = remote_run(host, f"rm -r {d}")
            if errcode!=0:
                print(f"WARNING: Failed to remove {d} on machine {host}")

    parallel_map(config["hosts"], do_cleanup)
