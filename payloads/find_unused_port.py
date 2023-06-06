#!/usr/bin/env python3
import socket
import sys
from typing import List


def check_used(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    if result == 0:
        sock.close()
        return True
    else:
        return False


def alloc(start_from: int = 12345, count: int=1) -> List[int]:
    res = []
    while len(res) < count:
        if not check_used(start_from):
            res.append(start_from)
        start_from += 1
    return res


print(",".join(str(a) for a in alloc(int(sys.argv[1]), int(sys.argv[2]))))
