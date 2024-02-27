import os
import string
import random
from .utils import get_relative_path
from .config import config
from .process_tools import remote_run
from .parallel_map import parallel_map
from .payload import send_payload, get_bindir
from typing import Optional
import datetime
import math
import wandb
import datetime
import subprocess
import requests
import json
import pyotp
import base64

known_dirs = {}


def get_wandb_sweep_command_without_args(sweep_id):
    api = wandb.Api()
    s = api.sweep(sweep_id)
    program = s.config["program"]
    cmd = []
    for c in s.config["command"]:
        if c in {'${env}', '${args}'}:
            continue
        elif c == '${program}':
            cmd.append(program)
        elif c.startswith("$"):
            assert False, f"Don't know how to handle arg {c}"
        else:
            cmd.append(c)
    return " ".join(cmd)


def install_helper():
    # sbatch allows queueuing only batch files, but not binaries, so we can't do sbatch <args> srun <cmd>. So make a
    # not_srun command which is a bash script that calls srun and passes all args to it
    send_payload(config["slurm"].keys(), "not_srun")


def get_slurm_target_full_path(hosts):
    tgtdirs = get_slurm_target_dir(hosts)

    def get_target_dir(host):
        tdir = tgtdirs[host]

        if config.is_local_run(host):
            curr_dir = os.getcwd()

            tdir = os.path.realpath(os.path.expanduser(tdir))
            curr_dir = os.path.realpath(os.path.expanduser(curr_dir))
            prefix = os.path.commonprefix([tdir, curr_dir])

            curr_rel = os.path.relpath(curr_dir, prefix)
            tdir = os.path.join(tdir, curr_rel)
        else:
            relpath = get_relative_path()[2:]
            tdir = os.path.join(tdir, relpath)

        return tdir
    
    return {h: get_target_dir(h) if h in tgtdirs else None for h in hosts}


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
            tdir = stdout.strip()

        return tdir

    res = parallel_map(to_query, get_hostname)

    known_dirs.update({k: v for k, v in zip(to_query, res)})
    return {h: known_dirs.get(h) for h in hosts}

def check_runtime(runtime: Optional[str]):
    assert runtime, "Need to specify expected runtime (-t, --runtime) for SLURM runs"

    rc=runtime.split(":")
    assert len(rc) == 3
    for r in rc:
        assert r.isdigit()

def run_agent(sweep_id: str, count: Optional[int], n_runs: Optional[int], multi_gpu: Optional[int],
              agents_per_gpu: Optional[int], runtime: Optional[str]):

    if not config.get("slurm"):
        return

    multi_gpu = multi_gpu or 1
    agents_per_gpu = agents_per_gpu or 1

    client_command = get_wandb_sweep_command_without_args(sweep_id) if multi_gpu > 1 else ""

    runs_for_count = int(math.ceil(count / agents_per_gpu)) if count else None
    n_run = min(runs_for_count, n_runs) if count is not None and n_runs is not None else (runs_for_count or n_runs or 1)

    wandb_env = config.get_wandb_env()
    assert wandb_env, "W&B API key is needed for staring a W&B swipe"

    check_runtime(runtime)

    tdirs = get_slurm_target_dir(config.get("slurm", {}).keys())

    id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    tstamp = f"{datetime.datetime.now():%Y_%m_%d_%H_%M_%S}"
    name = f"sweep_{sweep_id.replace('/','_')}_{tstamp}_{id}"

    print(f"Output will be written to {name}.log")

    def run_agent(host):
        target_dir = get_slurm_target_full_path([host])[host]
        
        modules = config["slurm"][host].get("modules")
        account = config["slurm"][host].get("account")
        bindir = get_bindir(host)

        odir = os.path.join(tdirs[host], config["slurm"][host].get("out_dir", "out"))

        sbatch = config.get_command(host, "sbatch")
        bash = config.get_command(host, "bash")
        wandb = config.get_command(host, "wandb", "~/.local/bin/wandb")
        env = config.get_env(host)

        cmd = f"{wandb} agent {sweep_id}"

        if count:
            # Count is handled by SLURM
            cnt = f"1-{count}%{n_run}"
            cmd = f"{cmd} --count 1"
        else:
            cnt = f"1-{n_run}"

        if multi_gpu > 1:
            cmd = f"{bash} -ec 'if [ $SLURM_PROCID -eq 0 ]; then {cmd}; else {client_command}; fi'"

        account = f"--account={account}" if account else ""

        machine_exclude = get_machine_exclude_list(host)
        partition = get_partition(host)

        template = config["slurm"][host].get("template", "daint")

        if template == "daint":
            slurm_flags = config["slurm"][host].get("slurm_flags", "--constraint=gpu --switches=1")
            slurm_flags = f"{slurm_flags} --ntasks-per-node={agents_per_gpu} --nodes={multi_gpu}"
        elif template == "stanford":
            slurm_flags = config["slurm"][host].get("slurm_flags", "")
            if agents_per_gpu != 1:
                raise ValueError("agents_per_gpu != 1 not supported for stanford template")
            slurm_flags = f"{slurm_flags} --gres=gpu:{multi_gpu}"
        else:
            raise ValueError(f"Unknown template {template}")
        
        cmd = f"{wandb_env} {env} {sbatch} --job-name={name} {account} {slurm_flags} --time={runtime} --output {odir}/{name}.log --chdir={target_dir} --array={cnt}  {machine_exclude} {partition} {bindir}/not_srun {cmd}"

        if modules:
            module = config.get_command(host, "module")
            cmd = f"{module} load {' '.join(modules)}; {cmd}"

        remote_run(host, cmd)

    install_helper()
    parallel_map(config.get("slurm", {}).keys(), run_agent)

def get_machine_exclude_list(host):
    machine_include_list = config.slurm_machine_whitelist.get(host) if config.slurm_machine_whitelist else None
    if machine_include_list is not None:
        all_machines_list = config["slurm"][host].get("machines", [])
        if not all_machines_list:
            raise ValueError(f"Machine list is not defined for SLURM host {host}, but machine whitelist is not empty")
        
        all_machines = set(all_machines_list)
        if config.enabled_gpu_types is not None:
            gpu_type_list = config.config["slurm"][host].get("gpu_map", {})
            allowed_machines = set()
            for t in config.enabled_gpu_types:
                allowed_machines.update(gpu_type_list.get(t, []))

            machine_include_list = machine_include_list.intersection(allowed_machines)
        
        for machine in machine_include_list:
            if machine not in all_machines:
                raise ValueError(f"Unknown machine {machine}")
            all_machines.remove(machine)

        if not machine_include_list:
            raise ValueError(f"No machines match the specified criteria for SLURM host {host}")
        machine_exclude = f"--exclude={','.join(all_machines)}"
    else:
        machine_exclude = ""

    return machine_exclude

def get_partition(host):
    partition = config.slurm_partition
    if partition is None:
        partition = config["slurm"][host].get("default_partition")

    if partition is None:
        return ""
    
    pmap = config["slurm"][host].get("partition_map", {})
    partition = pmap.get(partition, partition)

    return f"--partition={partition}"

def resume(sweep_id: str, multi_gpu: Optional[int], agents_per_gpu: Optional[int], runtime: Optional[str],
           force: bool):
    if not config.get("slurm"):
        return

    sweep = wandb.Api().sweep(sweep_id)
    r_to_start = [r for r in sweep.runs if ((force and r.state!="running") or r.state=="crashed")]
    n_run = len(r_to_start)

    if n_run == 0:
        print("No jobs to resume.")
        return

    print(f"Resuming {n_run} jobs.")

    multi_gpu = multi_gpu or 1
    agents_per_gpu = agents_per_gpu or 1

    assert agents_per_gpu == 1, "agents_per_gpu != 1 not supported for resume"

    check_runtime(runtime)

    wandb_env = config.get_wandb_env()
    assert wandb_env, "W&B API key is needed for staring a W&B swipe"

    tdirs = get_slurm_target_dir(config.get("slurm", {}).keys())
    ckpt_dir = config.get("wandb_ckpt_path", "wandb/*${id}*/files/checkpoint")
    resume = config.get("resume_command", "--restore ${ckpt}")

    cmd_base = get_wandb_sweep_command_without_args(sweep_id)

    name = f"resume_{sweep.id}"

    def run_agent(host):
        target_dir = get_slurm_target_full_path([host])[host]

        modules = config["slurm"][host].get("modules")
        account = config["slurm"][host].get("account")
        bindir = get_bindir(host)

        odir = os.path.join(tdirs[host], config["slurm"][host].get("out_dir", "out"))
        sbatch = config.get_command(host, "sbatch")
        bash = config.get_command(host, "bash")
        env = config.get_env(host)

        cmd = f"resume_jobs.py {sweep_id} '{ckpt_dir}' '{cmd_base} {resume}' {int(force)}"

        cnt = f"1-{n_run}"

        if multi_gpu > 1:
            bashcmd = f"if [ $SLURM_PROCID -eq 0 ]; then {cmd}; else pwd; {cmd_base}; fi"
            cmd = f"'echo {base64.b64encode(bashcmd.encode()).decode()}|base64 -d|bash'"

            cmd = f"{bash} -ec 'echo {base64.b64encode(bashcmd.encode()).decode()}|base64 -d|bash'"

        template = config["slurm"][host].get("template", "daint")

        machine_exclude = get_machine_exclude_list(host)
        partition = get_partition(host)

        if template == "daint":
            slurm_flags = config["slurm"][host].get("slurm_flags", "--constraint=gpu --switches=1")
            slurm_flags = f"{slurm_flags} --ntasks-per-node={agents_per_gpu}  --nodes={multi_gpu}"
        elif template == "stanford":
            slurm_flags = config["slurm"][host].get("slurm_flags", "")
            if agents_per_gpu != 1:
                raise ValueError("agents_per_gpu != 1 not supported for stanford template")
            slurm_flags = f"{slurm_flags} --gres=gpu:{multi_gpu}"
        else:
            raise ValueError(f"Unknown template {template}")
        
        account = f"--account={account}" if account else ""
        
        cmd = f"{wandb_env} {env} {sbatch} --job-name={name} {slurm_flags} {account} --time={runtime} --output {odir}/{name}.log --chdir={target_dir} --array={cnt} {machine_exclude} {partition} {bindir}/not_srun {cmd}"
        
        if modules:
            module = config.get_command(host, "module")
            cmd = f"{module} load {' '.join(modules)}; {cmd}"

        remote_run(host, cmd)

    install_helper()
    enabled_slurm_hosts = [k for k in config.get("slurm", {}).keys() if k in config.get_all_hosts()]
    send_payload(enabled_slurm_hosts, "resume_jobs.py")
    parallel_map(enabled_slurm_hosts, run_agent)


def check_login(host: str):
    # Define the command to run
    command = ['ssh', '-o', 'BatchMode=yes', host, 'exit']

    # Run the command and capture its output and exit status
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process.returncode == 0


def update_cscs_ssh_keys(host: str):
    secret = config["slurm"][host]["cscs_auth"]

    otp = pyotp.TOTP(secret["otp_secret"]).now()

    resp = requests.post(
        'https://sshservice.cscs.ch/api/v1/auth/ssh-keys/signed-key', 
        data=json.dumps({
            "username": secret["username"],
            "password": secret["password"],
            "otp": otp
        }), 
        headers={'Content-Type': 'application/json', 'Accept':'application/json'}, verify=True)

    if resp.status_code != requests.codes.ok:
        raise SystemExit("Error: Unable to fetch the SSH keys.")

    data = resp.json()
    with open(os.path.expanduser("~/.ssh/id_rsa_cscs"), "w") as f:
        f.write(data["private"])

    with open(os.path.expanduser("~/.ssh/id_rsa_cscs.pub"), "w") as f:
        f.write(data["public"])


def update_slurm_authentication():
    if not config.get("slurm"):
        return

    hosts_with_auth = [h for h in config.get("slurm", {}).keys() if "cscs_auth" in  config["slurm"][h]]

    auth_state = parallel_map(hosts_with_auth, check_login)
    unauthenticated_hosts = [h for h, a in zip(hosts_with_auth, auth_state) if not a]

    if not unauthenticated_hosts:
        return

    print(f"The following hosts require updating CSCS authentication: {','.join(unauthenticated_hosts)}")
    for h in unauthenticated_hosts:
        update_cscs_ssh_keys(h)

