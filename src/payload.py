import os
from .config import config
from .process_tools import remote_run
from .parallel_map import parallel_map
import base64


def get_bindir(host):
    return config.get("bin_dir", {}).get(host, "~/.local/bin")


def send_payload(hosts, name: str):
    # sbatch allows queueuing only batch files, but not binaries, so we can't do sbatch <args> srun <cmd>. So make a
    # not_srun command which is a bash script that calls srun and passes all args to it
    with open(os.path.dirname(os.path.abspath(__file__)) + f"/../payloads/{name}", "rb") as file:
        payload = base64.b64encode(file.read()).decode()

    def install_to_host(host):
        tdir = get_bindir(host)
        mkdir = config.get_command(host, "mkdir")
        base64 = config.get_command(host, "base64")
        echo = config.get_command(host, "echo")
        bash = config.get_command(host, "bash")
        chmod = config.get_command(host, "chmod")

        remote_run(host, f"{mkdir} -p {tdir}")
        remote_run(host, f"{bash} -c \"{echo} {payload} |{base64} -d > {tdir}/{name}\"")
        remote_run(host, f"{chmod} +x {tdir}/{name}")

    parallel_map(hosts, install_to_host)
