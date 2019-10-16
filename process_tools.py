import subprocess
from parallel_map import parallel_map_dict
import socket
import re
from config import config
import os
from utils import *

DEBUG = False

def run_process(command):
    if DEBUG:
        print("RUN: ", command)
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
    stdout = proc.communicate()[0].decode()
    return stdout, proc.returncode


def remote_run(host, command):
    env = config.get_env(host)
    command = env+" "+command

    if not is_local(host):
        command = "ssh "+host+" '"+command.replace("'","\'")+"'"

    return run_process(command)


def remote_run_alternative(host, command):
    command = command.split(" ")
    cmd = command[0]
    args = " ".join(command[1:])

    cmd = config.get_command(host, cmd) + " " + args
    return remote_run(host, cmd)


def run_multiple_hosts(hosts, command, relative=True):
    dir = get_relative_path()

    def run_it(host):
        cd = config.get_command(host, "cd")
        if relative:
            cmd = cd + " " + dir + " 2>/dev/null; " + command
        else:
            cmd = command

        return remote_run(host, cmd)

    return parallel_map_dict(hosts, run_it)


def run_multiple_on_multiple(hosts, command):
    def run_commands(host):
        out=[]
        for c in command:
            stdout, err = remote_run(host, c)
            if err!=0:
                print("WARNING: command %s failed on host %s" % (c, host))
                return (out, err)

            out.append(stdout)

        return (out, 0)

    return parallel_map_dict(hosts, run_commands)

