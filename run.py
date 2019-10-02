#!/usr/bin/env python3

from detect_gpus import get_free_gpu_list
import argparse
from remote_process import run_multiple_on_multiple, run_multiple_hosts

import json
with open('cluster.json') as json_file:
    cluster_config = json.load(json_file)

parser = argparse.ArgumentParser(description='Run on cluster')
parser.add_argument('command', metavar='N', type=str, nargs='*',
                    help='The command')
parser.add_argument('--setup', default=False, action='store_true')
parser.add_argument('-m', '--hosts', type=str, help="Run only on these machines. Start with ~ to invert. ~kratos skips kratos.")

args = parser.parse_args()

def filter_hosts():
    if args.hosts is not None:
        hosts = args.hosts.strip()
        invert = hosts[0] in ["!", "~"]
        if invert:
            hosts = hosts[1:]

        hosts = hosts.split(",")

        def any_starts_with(l, s):
            for a in l:
                if s.startswith(a):
                    return True

            return False

        if invert:
            filter_fn = lambda x: not any_starts_with(hosts, x)
        else:
            filter_fn = lambda x: any_starts_with(hosts, x)

        cluster_config["machines"] = list(filter(filter_fn, cluster_config["machines"]))
        print("Using hosts: ", " ".join(cluster_config["machines"]))

filter_hosts()

if args.setup:
    print("Running setup")
    res = run_multiple_on_multiple(cluster_config["machines"], cluster_config["setup"])
    print("Setup done.")

# print(get_free_gpu_list(cluster_config["machines"]))

if args.command:
    cmd = " ".join(args.command)
    res = run_multiple_hosts(cluster_config["machines"], cmd)

    for host, (stdout, err) in res.items():
        print("---------------- %s ----------------" % host)
        print(stdout)
        if err!=0:
            print("  WARNING: Command returned with error code %d" % err)