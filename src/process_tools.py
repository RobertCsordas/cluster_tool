import subprocess
from .parallel_map import parallel_map_dict
import socket
import re
from .config import config
import os
from .utils import *
from threading import Semaphore, Lock
from typing import Optional
import base64


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


def run_process(command, get_stderr=False, input: Optional[str] = None):
    if DEBUG:
        print("RUN: ", command)
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE if get_stderr else None,
                            shell=True, stdin=subprocess.PIPE)
    res = proc.communicate(input.encode() if input is not None else None)
    stdout = res[0].decode()
    if get_stderr:
        stderr = res[1].decode()
        return stdout, stderr, proc.returncode
    else:
        return stdout, proc.returncode

def remote_run(host, command, alternative=True, root_password: Optional[str] = None, add_sudo = True):
    # command = command.replace("'", "'\"'\"'")
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

    if root_password is not None and add_sudo:
        command = "sudo " + command

    export = config.get_command(host, "export")
    extra_path = ":".join(config.get("path", []))
    if extra_path:
        command = f"{export} PATH={extra_path}:$PATH; {command}"
    command = env+" "+command

    if "'" in command:
        # Avoid the impossible task of figuring out how to escape the string.
        command = f"echo {base64.b64encode(command.encode()).decode()}|base64 -d|bash"

    if not is_local(host):
        flags = config.get_ssh_flags(host)
        command = f"ssh {flags}"+(" -tt" if root_password else "")+" "+host+" '"+command+"'"

    with HostCallLimiter(host):
        stdout, errcode = run_process(command, input=(root_password + "\n") if root_password else None)
        if root_password:
            stdout=stdout.replace(root_password, "")
        return stdout, errcode


def run_multiple_hosts(hosts, command, relative=True, alternative=True, root_password: Optional[str] = None):
    dir = get_relative_path()

    def run_it(host):
        cd = config.get_command(host, "cd")

        cmd = command
        if root_password:
            cmd = "sudo "+cmd

        if relative:
            cmd = cd + " " + dir + " 2>/dev/null; " + cmd        

        return remote_run(host, cmd, alternative=alternative, root_password=root_password, add_sudo=False)

    return parallel_map_dict(hosts, run_it)


def run_multiple_on_multiple(hosts, command, root_password: Optional[str] = None):
    def run_commands(host):
        out=[]
        for c in command:
            stdout, err = remote_run(host, c, root_password=root_password)
            if err!=0:
                print("WARNING: command %s failed on host %s" % (c, host))
                return (out, err)

            out.append(stdout)

        return (out, 0)

    return parallel_map_dict(hosts, run_commands)
