from subprocess import run
from typing import Optional, Tuple, List, Set, Dict, Any
from .detect_gpus import get_top_gpus
from .config import config
from .utils import get_relative_path, get_command
from .process_tools import remote_run, run_process, run_multiple_hosts
from .parallel_map import parallel_map
from .sync import copy_local_dir
import math
import socket
import tempfile
import os
import wandb
from gql import gql
from . import slurm
import yaml
from .payload import send_payload


def get_config_count(file: str) -> Optional[int]:
    with open(file, "r") as f:
        config = yaml.safe_load(f)

    return get_config_count_from_dict(config)


def get_config_count_from_dict(config: Dict[str, Any]) -> Optional[int]:
    if config.get("method", "").lower() != "grid":
        return None

    n_config = 1
    for _, pval in config["parameters"].items():
        if "values" in pval:
            n_config *= len(pval["values"])
        elif "value" not in pval:
            # Can only handle enumerations so far.
            return None

    return n_config


def run_agent_local(sweep_id: str, count: Optional[int], n_runs: Optional[int], multi_gpu: Optional[int],
              agents_per_gpu: Optional[int], force_gpus: bool):

    agents_per_gpu = agents_per_gpu or 1
    multi_gpu = multi_gpu or 1
    relpath = get_relative_path()

    gpu_for_count = int(math.ceil(count / agents_per_gpu)) if count else None
    use_gpus = get_top_gpus(gpu_for_count if n_runs is None else (n_runs if count is None else
                            min(gpu_for_count, n_runs)), gpu_per_run=multi_gpu, ignore_used=force_gpus)

    wandb_key = config.get_wandb_env()
    assert wandb_key, "W&B API key is needed for staring a W&B swipe"

    all_gpus = []
    for h, g in use_gpus.items():
        remaining = g
        while len(remaining) >= multi_gpu:
            for index in range(agents_per_gpu):
                all_gpus.append((h, remaining[:multi_gpu], index))
            remaining = remaining[multi_gpu:]

    if not all_gpus:
        return
    count = f"--count {int(math.ceil(count / len(all_gpus)))}" if count else ""

    # Count how many multi-gpu runs are per host, and create an unique id for all of them
    all_gpus2 = all_gpus
    all_gpus = []
    count_per_host = {}
    for h, g, i in all_gpus2:
        within_host_index = count_per_host.get(h, 0)
        all_gpus.append((h, g, i, within_host_index))
        if len(g) > 1:
            count_per_host[h] = within_host_index + 1

    # Allocate ports for communicaiton
    send_payload(list(count_per_host.keys()), "find_unused_port.py")
    def alloc_ports(args):
        host, count = args
        port, errcode = remote_run(host, f"find_unused_port.py 12345 {count}")
        assert errcode == 0, "Failed to find unused port"
        return host, [int(p) for p in port.split(",")]

    if len(count_per_host):
        ports = parallel_map([(h, c) for h, c in count_per_host.items()], alloc_ports)
        ports = {h: c for h, c in ports}


    def start_wandb_client(arg: Tuple[str, List[int], int, int]):
        host, gpus, index, hi = arg

        cd = config.get_command(host, "cd")
        screen = config.get_command(host, "screen")
        wandb = config.get_command(host, "wandb", "~/.local/bin/wandb")
        env = config.get_env(host)

        gpus = [str(g) for g in gpus]

        prefix = f"{cd} {relpath}; {wandb_key} {env}"
        cmd = f"{wandb} agent {sweep_id} {count}"
        if len(gpus) > 1:
            client_command = slurm.get_wandb_sweep_command_without_args(sweep_id)

            for i in range(len(gpus)):
                distenv = f"CUDA_VISIBLE_DEVICES={gpus[i]} WORLD_SIZE={len(gpus)} RANK={i} LOCAL_RANK=0 MASTER_ADDR=127.0.0.1 MASTER_PORT={ports[host][hi]}"
                start_prefix = f"{prefix} {distenv} {screen} -d -S " + \
                               f"wandb_sweep_{sweep_id.split('/')[-1]}_gpu_{'_'.join(gpus)}_{i} -m "
  
                if i == 0:
                    gcmd = start_prefix + cmd
                else:
                    gcmd = start_prefix + client_command

                _, errcode = remote_run(host, gcmd + " 2>/dev/null")
                if errcode != 0:
                    print(f"Failed to start Multi-GPU W&B client on {host} (command: {cmd}), local rank {i}")
                    if i != 0:
                        print(f"WARNING: Already started {i} workers. Please kill them manually or wait for them to time-out.")
        else:
            per_gpu_index = f"_i{index}" if agents_per_gpu > 1 else ""
            cmd = f"{prefix} CUDA_VISIBLE_DEVICES='{','.join(gpus)}' {screen} -d -S " + \
                f"wandb_sweep_{sweep_id.split('/')[-1]}_gpu_{'_'.join(gpus)}{per_gpu_index} -m {cmd}"

            _, errcode = remote_run(host, cmd + " 2>/dev/null")

            if errcode != 0:
                print("Failed to start W&B client on %s (command: %s)" % (host, cmd))

    parallel_map(all_gpus, start_wandb_client)


def run_agent(sweep_id: str, count: Optional[int], n_runs: Optional[int], multi_gpu: Optional[int],
              agents_per_gpu: Optional[int], runtime: Optional[str], force_gpus: bool, exclude_machines: Set[str]):

    copy_local_dir()
    run_agent_local(sweep_id, count, n_runs, multi_gpu, agents_per_gpu, force_gpus=force_gpus)
    if config.slurm_enabled:
        slurm.run_agent(sweep_id, count, n_runs, multi_gpu, agents_per_gpu, runtime, exclude_machines)


def create_sweep(name, config_file):
    localhost = socket.gethostname()
    wandb = config.get_command(localhost, "wandb", get_command("wandb", "~/.local/bin/wandb"))

    project = config.get("wandb", {}).get("project")
    assert project is not None, "wandb/project must be specified in order to be able to start sweeps"
    
    if "/" in project:
        entity, project = project.split("/")
    else:
        entity = None

    with open(config_file, "r") as f:
        config_data = f.read()

    if config.get("wandb", {}).get("add_name_argument", False):
        config_data += "\n"
        config_data += "  name:\n"
        config_data += f"   value: sweep_{name}\n"

    file, tmpname = tempfile.mkstemp(".yaml", text=True)
    os.close(file)
    try:
        with open(tmpname, "w") as f:
            f.write(config_data)
            f.close()

        entity = f"--entity {entity}" if entity else ""

        stdout, stderr, err = run_process(f"{wandb} sweep --project {project} {entity} --name {name} {tmpname}", get_stderr=True)
    finally:
        os.remove(tmpname)

    if err!=0:
        assert False, "Failed to create sweep. Output: \n"+stdout+stderr

    sweep_id = stderr.split(" ")[-1].strip()
    print(f"Created sweep with ID: {sweep_id}")

    return sweep_id


def sweep(name: str, config_file: str, count: Optional[int], n_gpus: Optional[int], multi_gpu: Optional[int],
          agents_per_gpu: Optional[int], runtime: Optional[str], force_gpus: bool, exclude_machines: Set[str]):

    sweep_id = create_sweep(name, config_file)
    run_agent(sweep_id, count, n_gpus, multi_gpu, agents_per_gpu, runtime, force_gpus, exclude_machines)


def find_entity_and_project(project: str) -> Tuple[str, str]:
    if "/" in project:
        pieces = project.split("/")
        assert len(pieces) == 2 and min(len(p) for p in pieces) > 1, f"Invalid project specification: {project}"
        return tuple(pieces)
    else:
        return wandb.InternalApi().viewer()["entity"], project

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
    entity, project = find_entity_and_project(project)

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


def get_sweep_table(api: wandb.Api, project: str) -> Dict[str, str]:
    QUERY = gql('''       
    query Sweep($project: String!, $entity: String) {
        project(name: $project, entityName: $entity) {
            sweeps {
                edges {
                    node {
                        name
                        displayName
                        config
                    }
                }
            }
        }
    }''')

    entity, project = find_entity_and_project(project)

    response = api.client.execute(QUERY, variable_values={
        'entity': entity,
        'project': project,
    })

    edges = response.get("project", {}).get("sweeps", {}).get("edges")
    assert edges

    id_to_name  = {}
    for sweep in edges:
        sweep = sweep["node"]

        name = sweep["displayName"]
        if name is None:
            name = [s for s in sweep["config"].split("\n") if s.startswith("name:")]
            assert len(name)==1
            name = name[0].split(":")[1].strip()

        id_to_name[sweep["name"]] = name

    return id_to_name


def invert_sweep_id_table(t: Dict[str, str]) -> Tuple[Dict[str, str], Set[str]]:
    repeats = set()
    res = {}
    for id, name in t.items():
        if name in res:
            repeats.add(name)

        res[name] = id

    for r in repeats:
        del res[r]

    return res, repeats


def get_runs_in_sweep(api, project, sweep_id: Optional[str], filter: Dict = {}):
    f = {"sweep": sweep_id} if sweep_id else {}
    f.update(filter)
    return list(api.runs(project, f))


def get_run_host(api: wandb.Api, project: str, run_id: str) -> Dict[str, str]:
    QUERY = gql('''       
    query Run($projectName: String!, $entityName: String, $runName: String!) {
        project(name: $projectName, entityName: $entityName) {
            run(name: $runName) {
                host
            }
        }
    }''')

    entity, project = find_entity_and_project(project)

    response = api.client.execute(QUERY, variable_values={
        'entityName': entity,
        'projectName': project,
        'runName': run_id,
    })

    host = response.get("project", {}).get("run", {}).get("host")

    found = [h for h in config["hosts"] if h.startswith(host)] if host else []
    return found[0] if len(found) == 1 else None


def sync_crashed(sweep_name: Optional[str]):
    wandb_key = config.get_wandb_env()
    assert wandb_key, "W&B API key is needed for staring a W&B swype"

    project = config.get("wandb", {}).get("project")
    api = wandb.Api()

    if sweep_name is not None:
        sweep_map = get_sweep_table(api, project)
        name_to_id, repeats = invert_sweep_id_table(sweep_map)

        if sweep_name in name_to_id:
            sweep_name = name_to_id[sweep_name]
        elif sweep_name in repeats:
            print(f"ERROR: ambigous sweep name: {sweep_name}")
            return

    relpath = get_relative_path()
    
    runs = get_runs_in_sweep(api, project, sweep_name, {"state": "crashed"})
    print(f"Sweep {sweep_name}: found {len(runs)} crashed runs. Trying to synchronize...")
    for r in runs:
        hostname = get_run_host(api, project, r.id)
        dir = None
        found = []

        cmd = f"find ./wandb -iname '*{r.id}'"
        if hostname is None:
            res = run_multiple_hosts(config["hosts"], cmd)
            for hn, (res, retcode) in res.items():
                res = res.strip()
                if retcode == 0 and res:
                    found.append((hn, res))
        else:
            res, retcode = run_multiple_hosts([hostname], cmd)[hostname]
            res = res.strip()
            if retcode == 0 and res:
                found = [(hostname, res)]

        if len(found) != 1:
            print(f"WARNING: Failed to identify run {r.id}")
            continue
        
        hostname, dir = found[0]

        if len(dir.split("\n")) != 1:
            print(f"WARNING: Failed to identify run {r.id}")
            continue

        print(f"Found run {r.id} at {hostname} in dir {dir}. Syncing...")

        cd = config.get_command(hostname, "cd")
        wandb_cmd = config.get_command(hostname, "wandb", "~/.local/bin/wandb")
        env = config.get_env(hostname)

        cmd = f"{cd} {relpath}; {wandb_key} {env} {wandb_cmd} sync {dir}"
        _, errcode = remote_run(hostname, cmd + " 2>/dev/null")

        if errcode != 0:
            print("Sync failed :(")
            continue


def remove_artifacts(id: str):
    api = wandb.Api()
    run = api.run(id)
    artifacts = run.logged_artifacts(per_page=10000)

    for a in artifacts:
        a.delete()


def get_config_count_from_sweepid(sweep_id: str) -> Optional[int]:
    api = wandb.Api()
    s = api.sweep(sweep_id)
    return get_config_count_from_dict(s.config)
