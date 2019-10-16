from config import config
from process_tools import run_multiple_hosts, remote_run
from detect_gpus import get_free_gpu_list
from parallel_map import parallel_map
from sync import copy_local_dir, gather_relative
from screen import run_in_screen, wait_for_screen_shutdown, get_screen_name
from utils import expand_args
import socket


def check_used(port, host="127.0.0.1"):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex((host, port))
    if result == 0:
        sock.close()
        return True
    else:
        return False


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


def start_ray(n_gpus, ignore_if_running=False):
    head = config["ray"]["head"]
    port = config["ray"]["port"]

    if check_used(port, head):
        if ignore_if_running:
            return

        print("Port %d already open on host %s. Refusing to start the cluster. Isn't it running already?" % (port, head))
        return

    users = run_multiple_hosts(config["hosts"], "echo -n $USER")
    users = {k: v[0] for k, v in users.items()}

    use_gpus = get_top_gpus(n_gpus)

    head_gpus = use_gpus.get(head)
    del use_gpus[head]

    python3 = config.get_command(head, "python3")
    ray = config.get_command(head, "ray", "~/.local/bin/ray")
    nohup = config.get_command(head, "nohup")

    _, errcode = remote_run(head, "CUDA_VISIBLE_DEVICES=" + (",".join([str(h) for h in head_gpus])) +
                            " "+nohup+" "+python3+" "+ray+" start --head --redis-port="+str(port)+
                            " --temp-dir=/tmp/ray_"+users[head]+" 2>/dev/null")
    if errcode!=0:
        print("Failed to start ray head node.")
        return

    def start_ray_client(a):
        host, gpus = a

        python3 = config.get_command(host, "python3")
        ray = config.get_command(host, "ray", "~/.local/bin/ray")
        nohup = config.get_command(host, "nohup")

        cmd = "CUDA_VISIBLE_DEVICES=" + (",".join([str(g) for g in gpus])) +\
              " "+nohup+" "+python3+" "+ray+" start --address=" + head + ":" + str(port) + \
              " --temp-dir=/tmp/ray_" + users[head]
        _, errcode = remote_run(host, cmd+" 2>/dev/null")

        if errcode!=0:
            print("Failed to start ray client on %s (command: %s)" % (host, cmd))

    parallel_map([(h, g) for h, g in use_gpus.items()], start_ray_client)


def stop_ray():
    def stop_host(host):
        python3 = config.get_command(host, "python3")
        ray = config.get_command(host, "ray", "~/.local/bin/ray")
        remote_run(host, python3+" "+ray+" stop")

    parallel_map(config["hosts"], stop_host)


def ray_run(n_gpus, name, command, wait=True):
    start_ray(n_gpus, ignore_if_running=True)
    copy_local_dir()

    head = config["ray"]["head"]
    res, screen_name = run_in_screen([head], command, name)
    msg, errcode = res[head]
    if errcode!=0:
        print("Failed to start ray task %s on head node %s" % (command, head))
        return False

    if wait:
        print("Ray training started. Waiting to finish...")
        result_dir = expand_args(command, config["ray"]["result_directory"])
        wait_for_screen_shutdown([head], screen_name)
        ray_postprocess(config["hosts"], result_dir)
        print("Done.")

    return True


def ray_postprocess(hosts, result_directory):
    vars = {"result_directory": result_directory}
    print("Postprocess: Gathering ray results...")
    if not gather_relative(result_directory, hosts, "sequential"):
        print("Failed to sync ray result folders %s" % result_directory)
        return False

    print("Postprocess: Running post-training commands...")
    for cmd in config["ray"].get("process_results"):
        cmd = expand_args(vars, cmd)
        stdout, errcode = remote_run("localhost", cmd)
        if errcode!=0:
            print(stdout)
            print("Command %s failed" % cmd)
            return False
