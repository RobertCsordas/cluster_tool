import subprocess
from .parallel_map import parallel_map_dict
import socket
import re
from .config import config
import os
from .utils import *
from threading import Semaphore, Lock

DEBUG = False

class HostCallLimiter:
    host_active_connections_mutex = Lock()
    host_semaphores = {}
    N_CONNECTIONS_PER_HOST = 8

    def __init__(self, host: str):
        self.host = host

        HostCallLimiter.host_active_connections_mutex.acquire()
        if self.host not in HostCallLimiter.host_semaphores:
            HostCallLimiter.host_semaphores[self.host] = Semaphore(self.N_CONNECTIONS_PER_HOST)
        HostCallLimiter.host_active_connections_mutex.release()


    def __enter__(self):
        HostCallLimiter.host_semaphores[self.host].acquire()

    def __exit__(self ,type, value, traceback):
        HostCallLimiter.host_semaphores[self.host].release()


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

    with HostCallLimiter(host):
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

