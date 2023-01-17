import subprocess
from typing import Dict, List, Optional
from .process_tools import remote_run
from .parallel_map import parallel_map_dict
from .config import config
import functools


def get_free_gpus(host: str, ignore_used: bool) -> Optional[List[int]]:
    nvidia_smi = config.get_command(host, "nvidia-smi")

    try:
        free = []
        stdout, ret = remote_run(host, nvidia_smi+" --query-compute-apps=gpu_uuid --format=csv,noheader,nounits")
        if ret!=0:
            return None

        uuids = [s.strip() for s in stdout.split("\n") if s]

        stdout, ret = remote_run(host, nvidia_smi+" --query-gpu=index,uuid --format=csv,noheader,nounits")
        if ret != 0:
            return None

        id_uid_pair = [s.strip().split(", ") for s in stdout.split("\n") if s]

        for i in id_uid_pair:
            id, uid = i

            if uid not in uuids or ignore_used:
                free.append(int(id))

        return config.filter_gpus_host(host, free)
    except:
        return None


def get_free_gpu_list(ignore_used: bool):
    return parallel_map_dict(config["hosts"], functools.partial(get_free_gpus, ignore_used=ignore_used))


def get_top_gpus(n_runs: Optional[int], gpu_per_run: int = 1, ignore_used: bool = False) -> Dict[str, List[int]]:
    free_gpus = get_free_gpu_list(ignore_used)

    if n_runs is None:
        return free_gpus

    use_gpus = {}
    n_used = 0
    for host in config["hosts"]:
        this_gpus = free_gpus.get(host, [])
        use_gpus[host] = this_gpus[:n_runs * gpu_per_run - n_used]
        n_used += len(use_gpus[host]) // gpu_per_run
        if n_used >= n_runs:
            break

    return use_gpus
