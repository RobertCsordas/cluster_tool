import subprocess
from process_tools import remote_run
from parallel_map import parallel_map_dict

def get_free_gpus(host):
    try:
        free = []
        stdout, ret = remote_run(host, "nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader,nounits")
        if ret!=0:
            return None

        uuids = [s.strip() for s in stdout.split("\n") if s]

        stdout, ret = remote_run(host, "nvidia-smi --query-gpu=index,uuid --format=csv,noheader,nounits")
        if ret != 0:
            return None

        id_uid_pair = [s.strip().split(", ") for s in stdout.split("\n") if s]

        for i in id_uid_pair:
            id, uid = i

            if uid not in uuids:
                free.append(int(id))

        return free
    except:
        return None

def get_free_gpu_list(hosts):
    return parallel_map_dict(hosts, get_free_gpus)
