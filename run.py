#!/usr/bin/env python3

from detect_gpus import get_free_gpu_list
import argparse
import process_tools
from process_tools import run_multiple_on_multiple, run_multiple_hosts, run_in_screen
from sync import sync_curr_dir_multiple, gather_relative, copy_local_dir
import sys
from config import config
from ray import start_ray, stop_ray, ray_run
from setup import do_setup

parser = argparse.ArgumentParser(description='Run on cluster')
parser.add_argument('args', metavar='N', type=str, nargs='*', help='switch dependet args')
#parser.add_argument('--setup', default=False, action='store_true')
#parser.add_argument('--copy', default=False, action='store_true', help="copy current directory to all the servers")
#parser.add_argument('--gather', default=False, action='store_true', help="copy back subdirectory form all the servers")
parser.add_argument('-m', '--hosts', type=str, help="Run only on these machines. Start with ~ to invert. ~kratos skips kratos.")
parser.add_argument('-p', '--postfix', default=False, action='store_true', help="Add machine name as postfix when gathering")
parser.add_argument('-g', '--n_gpus', type=int, help="Run ray on this many GPUs")
parser.add_argument('-n', '--name', type=str, help="Name for training")
parser.add_argument('-d', '--debug', default=False, action='store_true', help="Debug: display all the shell commands")

args = parser.parse_args()

process_tools.DEBUG = args.debug

config.filter_hosts(args.hosts)

def assert_arg_count(cnt, print_usage = lambda: None):
    if len(args.args)-1 != cnt:
        print("Command \""+args.args[0]+"\" needs %d arguments, but %d were given: \"%s\"" % \
              (cnt, len(args.args)-1," ".join(args.args[1:])))

        print_usage()
        sys.exit(-1)

if len(args.args)>0:
    if args.args[0] == "setup":
        assert_arg_count(0)

        print("Running setup")
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
        res = run_multiple_hosts(config["hosts"], cmd)

        for host, (stdout, err) in res.items():
            print("---------------- %s ----------------" % host)
            print(stdout)
            if err!=0:
                print("  WARNING: Command returned with error code %d" % err)

    elif args.args[0] == "ray":
        if len(args.args)<2:
            print("Usage: ray start/stop/run command")
            sys.exit(-1)

        if args.args[1] == "start":
            start_ray(args.n_gpus)
        elif args.args[1] == "stop":
            stop_ray()
        elif args.args[1] == "run":
            ray_run(args.n_gpus, args.name, " ".join(args.args[2:]))
        else:
            assert False, "Invalid command: "+" ".join(args.args[1:])
    elif args.args[0] == "screen":
        if args.args[1] == "run":
            run_in_screen(config["hosts"], " ".join(args.args[1:]), name=args.name)
    else:
        print("Invalid command: "+" ".join(args.args))
