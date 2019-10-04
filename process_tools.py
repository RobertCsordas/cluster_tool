import subprocess
from parallel_map import parallel_map_dict
import socket
import re
from config import config
import os

DEBUG = False


def run_process(command):
    if DEBUG:
        print("RUN: ", command)
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
    stdout = proc.communicate()[0].decode()
    return stdout, proc.returncode


def remote_run(host, command):
    if host not in ["localhost", socket.gethostname()]:
        command = "ssh "+host+" '"+command.replace("'","\'")+"'"

    return run_process(command)


def run_multiple_hosts(hosts, command):
    return parallel_map_dict(hosts, lambda h: remote_run(h, command))


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


def run_in_screen(hosts, command, name = None, relative = True):
    if name is None:
        name = command
        name = re.sub('[^0-9a-zA-Z]+', '_', name)

    dir = "~/"+os.path.relpath(os.getcwd(), os.path.expanduser("~"))

    def run(host):
        cd = config.get_command(host, "cd")
        screen = config.get_command(host, "screen")
        cmd = screen + " -d -S "+name+" -m "+command
        if relative:
            cmd = cd + " '" + dir + "'; " + cmd
        return remote_run(host, cmd)

    return parallel_map_dict(hosts, run)
