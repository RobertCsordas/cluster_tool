from typing import Optional, Tuple
from .detect_gpus import get_top_gpus
from .config import config
from .utils import get_relative_path
from .process_tools import remote_run
from .parallel_map import parallel_map
from .sync import copy_local_dir
import math


def get_wandb_env() -> str:
    wandb = config.get("wandb", {}).get("apikey")
    if wandb is None:
        wandb = ""
    else:
        wandb = " WANDB_API_KEY=" + wandb + " "
    return wandb


def run(sweep_id: str, count: Optional[int], n_gpus: Optional[int]):
    relpath = get_relative_path()

    copy_local_dir(config["hosts"])
    use_gpus = get_top_gpus(count if n_gpus is None else (n_gpus if count is None else min(count, n_gpus)))

    wandb_key = get_wandb_env()
    assert wandb_key, "W&B API key is needed for staring a W&B swype"

    all_gpus = sum([[(h, gpu) for gpu in g] for h, g in use_gpus.items()], [])
    count = f"--count {int(math.ceil(count / len(all_gpus)))}" if count else ""

    def start_wandb_client(arg: Tuple[str, int]):
        host, gpu = arg

        cd = config.get_command(host, "cd")
        screen = config.get_command(host, "screen")
        wandb = config.get_command(host, "~/.local/bin/wandb")

        cmd = f"{cd} {relpath}; CUDA_VISIBLE_DEVICES={gpu} {wandb_key}  {screen} -d -S "+\
              f"wandb_sweep_{sweep_id.split('/')[-1]}_gpu_{gpu} -m " + \
              f"{wandb} agent {sweep_id} {count}"

        _, errcode = remote_run(host, cmd + " 2>/dev/null")

        if errcode != 0:
            print("Failed to start W&B client on %s (command: %s)" % (host, cmd))

    parallel_map(all_gpus, start_wandb_client)
