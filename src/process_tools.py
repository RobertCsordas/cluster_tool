import subprocess
from .parallel_map import parallel_map_dict
import socket
import re
from .config import config
import os
from .utils import *

DEBUG = False

def run_process(command, get_stderr=False):
    if DEBUG:
        print("RUN: ", command)
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE if get_stderr else None,
                            shell=True)
    res = proc.communicate()
    stdout = res[0].decode()
    if get_stderr:
        stderr = res[1].decode()
        return stdout, stderr, proc.returncode
    else:
        return stdout, proc.returncode

def remote_run(host, command, alternative=True):
    if alternative:
        commands = [c.strip() for c in command.split(";") if c]
        modified_commands = []
        for curr in commands:
            curr = curr.split(" ")
            cmd = curr[0]
            args = " ".join(curr[1:])

            modified_commands.append(config.get_command(host, cmd) + " " + args)

        command = ";".join(modified_commands)

    env = config.get_env(host)

    export = config.get_command(host, "export")
    extra_path = ":".join(config.get("path", []))
    if extra_path:
        command = f"{export} PATH=$PATH:{extra_path}; {command}"
    command = env+" "+command

    if not is_local(host):
        command = "ssh "+host+" '"+command.replace("'","\'")+"'"

    return run_process(command)


def run_multiple_hosts(hosts, command, relative=True, alternative=True):
    dir = get_relative_path()

    def run_it(host):
        cd = config.get_command(host, "cd")
        if relative:
            cmd = cd + " " + dir + " 2>/dev/null; " + command
        else:
            cmd = command

        return remote_run(host, cmd, alternative=alternative)

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

