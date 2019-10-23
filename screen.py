from parallel_map import parallel_map_dict
from process_tools import remote_run
from utils import *
from config import config
import re
import time

def is_screen_running(hosts, name):
    def check_for_sceen(host):
        screen = config.get_command(host, "screen")
        _, errcode = remote_run(host, "screen -ls "+name)
        return errcode==0
    return parallel_map_dict(hosts, check_for_sceen)


def wait_for_screen_shutdown(hosts, name):
    start_time = time.time()
    while True:
        running = is_screen_running(hosts, name)
        if not any(running.values()):
            return

        time.sleep(60)

    end_time = time.time()
    print("Finished in "+hms_string(end_time-start_time))


def get_screen_name(command, name):
    if name is None:
        c_parts = [c for c in command.split(" ") if c]
        name = command
        try:
            index = c_parts.index("-name")
            if index < len(c_parts)-1:
                name = c_parts[0]+"_"+c_parts[index+1]
        except:
            pass

    name = re.sub('[^0-9a-zA-Z]+', '_', name)
    return name[:69] + "_" + random_string(10)


def run_in_screen(hosts, command, name = None, relative = True, env = ""):
    name = get_screen_name(command, name)
    dir = get_relative_path()

    if isinstance(env, dict):
        edict = env
        env = ""
        for k, v in edict.items():
            env = k+"='"+v+"'"

    if env:
        env = env + " "

    def run(host):
        cd = config.get_command(host, "cd")
        screen = config.get_command(host, "screen")
        cmd = env + screen + " -d -S "+name+" -m "+command
        if relative:
            cmd = cd + " " + dir + "; " + cmd
        return remote_run(host, cmd)

    return parallel_map_dict(hosts, run), name