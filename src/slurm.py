import os
import string
import random
from .utils import get_relative_path
from .config import config
from .process_tools import run_multiple_hosts, remote_run
from .parallel_map import parallel_map
from typing import Optional
import datetime
import math

known_dirs = {}


def get_bindir(host):
    return config["slurm"][host].get("bin_dir", "~/.local/bin")


def install_helper():
    # sbatch allows queueuing only batch files, but not binaries, so we can't do sbatch <args> srun <cmd>. So make a
    # not_srun command which is a bash script that calls srun and passes all args to it
    def install_to_host(host):
        tdir = get_bindir(host)
        mkdir = config.get_command(host, "mkdir")
        base64 = config.get_command(host, "base64")
        echo = config.get_command(host, "echo")
        bash = config.get_command(host, "bash")

        remote_run(host, f"{mkdir} -p {tdir}")
        remote_run(host, f"{bash} -c \"{echo} IyEvYmluL2Jhc2gKc3J1biAkQAo= |{base64} -d > {tdir}/not_srun\"")

    parallel_map(config["slurm"].keys(), install_to_host)


def get_slurm_target_dir(hosts):
    hosts = list(hosts)
    sc = config.get("slurm", {})
    to_query = [h for h in hosts if h not in known_dirs and h in sc]

    def get_hostname(host):
        echo = config.get_command(host, "echo")
        tdir = config["slurm"][host]["target_dir"]
        if "$" in tdir:
            stdout, ret = remote_run(host, f"{echo} {tdir}")
            assert ret == 0
            return stdout.strip()
        else:
            return tdir

    res = parallel_map(to_query, get_hostname)

    known_dirs.update({k: v for k, v in zip(to_query, res)})
    return {h: known_dirs.get(h) for h in hosts}


def run_agent(sweep_id: str, count: Optional[int], n_gpus: Optional[int], multi_gpu: Optional[int],
              agents_per_gpu: Optional[int], runtime: Optional[str]):

    if not config.get("slurm"):
        return

    assert (multi_gpu or 1) == 1

    gpu_for_count = int(math.ceil(count / agents_per_gpu)) if count else None
    n_gpu = min(gpu_for_count, n_gpus) if count is not None and n_gpus is not None else (gpu_for_count or n_gpus or 1)

    agents_per_gpu = agents_per_gpu or 1

    wandb_env = config.get_wandb_env()
    assert wandb_env, "W&B API key is needed for staring a W&B swipe"

    assert runtime, "Need to specify expected runtime (-t, --runtime) for SLURM runs"

    rc=runtime.split(":")
    assert len(rc) == 3
    for r in rc:
        assert r.isdigit()

    tdirs = get_slurm_target_dir(config.get("slurm", {}).keys())

    id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    tstamp = f"{datetime.datetime.now():%Y_%m_%d_%H_%M_%S}"
    name = f"sweep_{sweep_id.replace('/','_')}_{tstamp}_{id}"

    print(f"Output will be written to {name}.log")

    relpath = get_relative_path()[2:]

    def run_agent(host):
        modules = config["slurm"][host].get("modules")
        account = config["slurm"][host]["account"]
        bindir = get_bindir(host)

        odir = os.path.join(tdirs[host], config["slurm"][host].get("out_dir", "out"))

        sbatch = config.get_command(host, "sbatch")
        wandb = config.get_command(host, "wandb", "~/.local/bin/wandb")

        cmd = f"{wandb_env} {sbatch} --job-name={name} --constraint=gpu --account={account} --time={runtime} --output {odir}/{name}.log --chdir={os.path.join(tdirs[host], relpath)} --ntasks={n_gpu} --ntasks-per-node={agents_per_gpu} {bindir}/not_srun {wandb} agent {sweep_id}"
        if modules:
            module = config.get_command(host, "module")
            cmd = f"{module} load {' '.join(modules)}; {cmd}"

        # print(cmd)
        remote_run(host, cmd)

    install_helper()
    parallel_map(config.get("slurm", {}).keys(), run_agent)
