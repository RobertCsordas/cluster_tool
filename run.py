#!/usr/bin/env python3

from detect_gpus import get_free_gpu_list
import argparse
from process_tools import run_multiple_on_multiple, run_multiple_hosts
from sync import sync_curr_dir_multiple, gather_relative
import sys
from config import config

parser = argparse.ArgumentParser(description='Run on cluster')
parser.add_argument('args', metavar='N', type=str, nargs='*', help='switch dependet args')
#parser.add_argument('--setup', default=False, action='store_true')
#parser.add_argument('--copy', default=False, action='store_true', help="copy current directory to all the servers")
#parser.add_argument('--gather', default=False, action='store_true', help="copy back subdirectory form all the servers")
parser.add_argument('-m', '--hosts', type=str, help="Run only on these machines. Start with ~ to invert. ~kratos skips kratos.")
parser.add_argument('-p', '--postfix', default=False, action='store_true', help="Add machine name as postfix when gathering")

args = parser.parse_args()

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
        res = run_multiple_on_multiple(config["machines"], cluster_config["setup"])
        print("Setup done.")

    elif args.args[0] == "copy":
        assert_arg_count(0)
        res = sync_curr_dir_multiple(config["machines"], "")
        for m, success in res.items():
            if not success:
                print("Failed to copy data to machine %s" % m)

    elif args.args[0] == "gather":
        def print_usage():
            print("Usage: gather <path>")

        gather_relative(args.args[1], config["machines"], "postfix" if args.postfix else "on_conflict_confirm")

    elif args.args[0] == "run":
        cmd = " ".join(args.args[1:])
        res = run_multiple_hosts(config["machines"], cmd)

        for host, (stdout, err) in res.items():
            print("---------------- %s ----------------" % host)
            print(stdout)
            if err!=0:
                print("  WARNING: Command returned with error code %d" % err)
