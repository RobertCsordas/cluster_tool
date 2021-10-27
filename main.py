#!/usr/bin/env python3

from src.detect_gpus import get_free_gpu_list
from src.remote_process import kill_pids, find_phantom_processes, kill_phantom_processes
import argparse
import src.process_tools
from src.process_tools import run_multiple_on_multiple, run_multiple_hosts
from src.sync import sync_curr_dir_multiple, gather_relative, copy_local_dir
import sys
from src.config import config
from src.setup import do_setup
from src.ssh_setup import setup_ssh_login
from src.screen import run_in_screen, is_screen_running
from src.utils import expand_args
from src import wandb_interface
import getpass
import os

parser = argparse.ArgumentParser(description='Run on cluster')
parser.add_argument('args', metavar='N', type=str, nargs='*', help='switch dependet args')
#parser.add_argument('--setup', default=False, action='store_true')
#parser.add_argument('--copy', default=False, action='store_true', help="copy current directory to all the servers")
#parser.add_argument('--gather', default=False, action='store_true', help="copy back subdirectory form all the servers")
parser.add_argument('-m', '--hosts', type=str, help="Run only on these machines. Start with ~ to invert. ~kratos skips kratos.")
parser.add_argument('-pf', '--postfix', default=False, action='store_true', help="Add machine name as postfix when gathering")
parser.add_argument('-g', '--n_gpus', type=int, help="Run ray on this many GPUs")
parser.add_argument('-n', '--name', type=str, help="Name for training")
parser.add_argument('-d', '--debug', default=False, action='store_true', help="Debug: display all the shell commands")
parser.add_argument('-c', '--count', type=int, help="count for wandb sweep")
parser.add_argument('-pg', '--per_gpu', type=int, default=1, help="W&B agents per GPU")
parser.add_argument('-mgpu', '--multi_gpu', type=int, default=1, help="Use this many GPUs per run")
parser.add_argument('-p', '--project', default="", help="Overwrite wandb project from the config file")
parser.add_argument('-s', '--slurm', default=False, action='store_true', help="Enable SLURM operations. Prevents accidental runs.")
parser.add_argument('-t', '--runtime', type=str, help="Expected runtime")

args = parser.parse_args()

src.process_tools.DEBUG = args.debug

config.set_slurm(args.slurm)
config.filter_hosts(args.hosts)
if args.project:
    config.update({"wandb": {"project": args.project}})


def assert_arg_count(cnt, print_usage = lambda: None):
    if len(args.args)-1 != cnt:
        print("Command \""+args.args[0]+"\" needs %d arguments, but %d were given: \"%s\"" % \
              (cnt, len(args.args)-1," ".join(args.args[1:])))

        print_usage()
        sys.exit(-1)


def run_on_all(command, root_password=None):
    res = run_multiple_hosts(config["hosts"], command, root_password = root_password)

    for host, (stdout, err) in res.items():
        print("---------------- %s ----------------" % host)
        print(stdout)
        if err != 0:
            print("  WARNING: Command returned with error code %d" % err)


if len(args.args)>0:
    if args.args[0] == "setup":
        do_login = True
        do_env = True

        if len(args.args)==2:
            if args.args[1]=="login":
                do_env = False
            elif args.args[1]=="env":
                do_login = False
            else:
                print("Invalid argument for setup: %s. Valid arguments: login/env" % args.args[1])
                sys.exit(-1)
        elif len(args.args)!=1:
            print("setup can have an optional argument login/env")
            sys.exit(-1)

        if do_login:
            print("Setting up automatic ssh login")
            setup_ssh_login(config["hosts"])

        if do_env:
            print("Running environment setup")
            do_setup()
        print("Setup done.")

    elif args.args[0] == "copy":
        assert_arg_count(0)
        copy_local_dir()

    elif args.args[0] == "gather":
        def print_usage():
            print("Usage: gather <path>")

        assert_arg_count(1, print_usage)
        gather_relative(args.args[1], config["hosts"], "postfix" if args.postfix else "on_conflict_confirm")

    elif args.args[0] == "run":
        cmd = " ".join(args.args[1:])
        run_on_all(cmd)
    elif args.args[0] == "sudo":
        pswd = getpass.getpass('Enter root password:')
        cmd = " ".join(args.args[1:])
        run_on_all(cmd, root_password=pswd)
    elif args.args[0] == "wandb":
        if args.args[1] == "agent":
            assert len(args.args) == 3, "Usage error: wandb agent <sweep id>"
            wandb_interface.run_agent(args.args[2], args.count, args.n_gpus, args.multi_gpu, args.per_gpu, args.runtime)
        elif args.args[1] == "sweep":
            if len(args.args) == 4:
                name = args.args[2]
                fname = args.args[3]
            elif len(args.args) == 3:
                fname = args.args[2]
                name = os.path.splitext(os.path.basename(fname))[0]
            else:
                assert False, "Usage error: wandb sweep <name> <config_file>\n<name> is optional"

            assert os.path.isfile(fname), f"File {fname} doesn't exists"
            wandb_interface.sweep(name, fname, args.count, args.n_gpus, args.multi_gpu, args.per_gpu, args.runtime)
        elif args.args[1] == "cleanup":
            if len(args.args) == 3:
                wandb_dir = args.args[2]
            else:
                wandb_dir = "wandb"

            wandb_interface.cleanup(wandb_dir)
        elif args.args[1] == "sync_crashed":
            if len(args.args) == 2:
                sweep_name = None
            elif len(args.args) == 3:
                sweep_name = args.args[2]
            else:
                assert False, "Usage error: wandb sync_crashed <sweep id or name>\n<sweep id or name> is optional"
            wandb_interface.sync_crashed(sweep_name)
        elif args.args[1] == "remove_artifacts":
            assert len(args.args) == 3, "Usage: wandb remove <run id>"
            wandb_interface.remove_artifacts(args.args[2])
        else:
            assert False, "Invalid command"
    elif args.args[0] == "screen":
        if args.args[1] == "run":
            copy_local_dir()
            run_in_screen(config["hosts"], " ".join(args.args[2:]), name=args.name)
    elif args.args[0] == "info":
        if len(args.args)<2:
            print("Usage: info torch")
            sys.exit(-1)

        if args.args[1]=="torch":
            run_on_all('python3 -c "import torch; print(torch.__version__)"')
        else:
            assert False, "Invalid command: "+args.args[1]
    elif args.args[0]=="list_phantom":
        for host, fproc in find_phantom_processes().items():
            print(f"Host: {host}")
            for user, pidlist in fproc.items():
                print(f"   {user}: {', '.join(pidlist)}")
    elif args.args[0]=="kill_phantom":
        kill_phantom_processes()      
    else:
        print("Invalid command: "+" ".join(args.args))
