import os
import socket

def get_relative_path():
    return "~/\'" + os.path.relpath(os.getcwd(), os.path.expanduser("~"))+"'"

def is_local(host):
    return host in ["localhost", socket.gethostname()]
