from config import config
from process_tools import run_multiple_hosts, remote_run
from detect_gpus import get_free_gpu_list
from parallel_map import parallel_map


def get_top_gpus(n_gpus):
    free_gpus = get_free_gpu_list()

    if n_gpus is None:
        return free_gpus

    use_gpus = {}
    n_used = 0
    for host in config["hosts"]:
        this_gpus = free_gpus.get(host, [])
        use_gpus[host] = this_gpus[:n_gpus - n_used]
        n_used += len(use_gpus[host])
        if n_used >= n_gpus:
            break

    return use_gpus


def start_ray(n_gpus):
    users = run_multiple_hosts(config["hosts"], "echo -n $USER")
    users = {k: v[0] for k, v in users.items()}

    use_gpus = get_top_gpus(n_gpus)

    head = config["ray"]["head"]
    port = config["ray"]["port"]

    head_gpus = use_gpus.get(head)
    del use_gpus[head]

    ray = config.get_command(head, "ray", "~/.local/bin/ray")
    nohup = config.get_command(head, "nohup")

    _, errcode = remote_run(head, "CUDA_VISIBLE_DEVICES=" + (",".join([str(h) for h in head_gpus])) +
                            " "+nohup+" "+ray+" start --head --redis-port="+str(port)+
                            " --temp-dir=/tmp/ray_"+users[head]+" 2>/dev/null")
    if errcode!=0:
        print("Failed to start ray head node.")
        return

    def start_ray_client(a):
        host, gpus = a

        ray = config.get_command(host, "ray", "~/.local/bin/ray")
        nohup = config.get_command(host, "nohup")

        cmd = "CUDA_VISIBLE_DEVICES=" + (",".join([str(g) for g in gpus])) +\
              " "+nohup+" "+ray+" start --address=" + head + ":" + str(port) + \
              " --temp-dir=/tmp/ray_" + users[head]
        _, errcode = remote_run(host, cmd+" 2>/dev/null")

        if errcode!=0:
            print("Failed to start ray client on %s (command: %s)" % (host, cmd))

    parallel_map([(h, g) for h, g in use_gpus.items()], start_ray_client)


def stop_ray():
    def stop_host(host):
        ray = config.get_command(host, "ray", "~/.local/bin/ray")
        remote_run(host, ray+" stop")

    parallel_map(config["hosts"], stop_host)
