import os
import subprocess
from utils import *
from process_tools import run_process

def setup_ssh_login(hosts):
    if not os.path.isfile(os.path.expanduser("~/.ssh/id_rsa.pub")):
        print("Public ID key not found. Generating...")

        proc = subprocess.Popen("ssh-keygen", stdin=subprocess.PIPE, stdout=subprocess.PIPE, shell=True)
        while proc.returncode is None:
            proc.communicate(input="\n".encode())

        if proc.returncode!=0:
            print("Generating key failed with error code %d. Try running ssh-keygen manually." % proc.returncode)
            return

    for h in hosts:
        if is_local(h):
            continue

        print("Copying id for host "+h)
        run_process("ssh-copy-id -i ~/.ssh/id_rsa.pub " + h)
