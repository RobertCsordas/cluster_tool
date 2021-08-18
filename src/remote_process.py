from typing import Dict, List, Optional
from .parallel_map import parallel_map_dict, parallel_map
from .config import config
from .process_tools import remote_run
import getpass


def get_usernames() -> List[str]:
    def get_name(host: str) -> str:
        whoami = config.get_command(host, "whoami")
        stdout, ret = remote_run(host, whoami)
        return stdout if ret != 0 else None

    return parallel_map_dict(config["hosts"], get_name)


def kill_pids(pids: Dict[str, List[int]], root_password: Optional[str] = None, gpid=False):
    def do_kill(args):
        host, pids = args
        kill = config.get_command(host, "kill")
        for p in pids:
            print("Killing", p)
            remote_run(host, f"{kill} {'-' if gpid else ''}{p}", root_password=root_password)

    return parallel_map([(k, v) for k, v in pids.items()], do_kill)


def find_phantom_processes() -> Dict[str, List[str]]:
    def find_dead(host: str) -> List[str]:
        ps = config.get_command(host, "ps")

        stdout, ret = remote_run(host, f"{ps} -o user,pgid,ppid,cmd -e")
        lines = [[w.strip() for w in l.split(" ") if w] for l in stdout.split("\n")]
        lines = [l for l in lines if l]

        parentless = [(l[0], l[1], l[3]) for l in lines[1:] if l[2] == "1"]
        parentless_python = [p for p in parentless if "python" in p[2] and p[0]!="root"]

        by_pgid = {}
        for (user, pgid, cmd) in parentless_python:
            if pgid in by_pgid:
                assert by_pgid[pgid][0] == user
            else:
                by_pgid[pgid] = (user, cmd)

        by_user = {}
        for k, v in by_pgid.items():
            if v[0] not in by_user:
                by_user[v[0]] = []

            by_user[v[0]].append(k)
        return by_user

    return {k: v for k, v in parallel_map_dict(config["hosts"], find_dead).items() if v}


def kill_phantom_processes():
    phantoms = find_phantom_processes()
    pswd = None

    if phantoms:
        usernames = get_usernames()
        need_sudo = False

        print("Found phantom processes:")
        all_pids = {}
        for host, fproc in phantoms.items():
            print(f"  Host: {host}")
            for user, pidlist in fproc.items():
                print(f"     {user}: {', '.join(pidlist)}")

            all_pids[host] = sum(fproc.values(), [])

            need_sudo = need_sudo or len(fproc) > 1 or usernames[host] not in fproc

        if need_sudo:
            while True:
                print("Needs to kill processes of other users. Do you want to kill them or just kill yours [y/N]?")
                inp = input().lower().strip()
                if inp in {"y", "n", ""}:
                    break

                print("Invalid choice.")

            if inp == "y":
                pswd = getpass.getpass('Enter root password:')
            else:
                all_pids = {k: v.get(usernames[k], []) for k, v in phantoms.items()}
                all_pids = {k: v for k, v in all_pids.items() if v}

        kill_pids(all_pids, root_password = pswd, gpid=True)
