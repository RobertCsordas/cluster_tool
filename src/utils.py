import os
import socket
import string
import random

def get_relative_path():
    return "~/\'" + os.path.relpath(os.getcwd(), os.path.expanduser("~"))+"'"

def is_local(host):
    return host in ["localhost", socket.gethostname()]

def random_string(length):
    letters_and_digits = string.ascii_letters + string.digits
    return ''.join(random.choice(letters_and_digits) for _ in range(length))

def expand_args(command_or_vars, expand_this, sanitize=lambda x: x):
    last_pos = -1
    res = ""

    if isinstance(command_or_vars, str):
        command_or_vars = [c.strip() for c in command_or_vars.split(" ") if c]

    while True:
        pos = expand_this.find("${", last_pos+1)
        if pos<0:
            res += expand_this[last_pos+1:]
            return res

        res += expand_this[last_pos+1: pos]
        close_pos = expand_this.find("}", pos+2)
        if close_pos<0:
            assert "Invalid expandable string '%s'. No closing bracket found." % expand_this

        name = expand_this[pos+2: close_pos]
        if not name:
            assert "Invalid expandable string '%s'. Name is empty." % expand_this

        if isinstance(command_or_vars, dict):
            var = command_or_vars.get(name)
            if var is None:
                assert False, "Undefined variable %s. Valid vars: %s" % (name, list(command_or_vars.keys()))
        else:
            if name not in command_or_vars:
                print("Failed to find %s in command %s" % (name, " ".join(command_or_vars)))
                return None

            i_name = command_or_vars.index(name)
            if i_name >= len(command_or_vars):
                print("There is no argument for %s in command %s" % (name, " ".join(command_or_vars)))
                return None

            var = command_or_vars[i_name+1]

        res += sanitize(var)
        last_pos = close_pos


def hms_string(sec_elapsed):
    h = int(sec_elapsed / (60 * 60))
    m = int((sec_elapsed % (60 * 60)) / 60)
    s = sec_elapsed % 60.
    return "{}:{:>02}:{:>05.2f}".format(h, m, s)
