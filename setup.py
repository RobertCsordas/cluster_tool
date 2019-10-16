from process_tools import run_multiple_on_multiple, remote_run
from config import config
from parallel_map import parallel_map

def do_env_setup(host):
    res, errcode = remote_run(host, "ls -d ~/.clustertool 2>/dev/null")
    if errcode!=0:
        res, errcode = remote_run(host, "mkdir -p ~/.clustertool/bin")
        if errcode!=0:
            print("Failed to create ~/.clustertool directory")
            return False

        res, errcode = remote_run(host, "ln -s ~/.local/bin/ray ~/.clustertool/bin/")
        if errcode!=0:
            print("Failed to link ray binary to the correct path")
            return False

        res, errcode = remote_run(host, "echo \'PATH=\\\"~/.clustertool/bin:\$PATH\\\"\' \>\>.bashrc")
        if errcode!=0:
            print("Failed to set up environment")
            return False


def do_setup():
    def run_setup(host):
        for s in config["setup"]:
            res, errcode = remote_run(host, s)
            if errcode:
                print(res)
                print("Setup command %s failed on host %s" % (s, host))
                return False

    parallel_map(config["hosts"], run_setup)
    parallel_map(config["hosts"], do_env_setup)
