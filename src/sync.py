import os
import shlex
from .process_tools import run_process, run_multiple_hosts
from .parallel_map import parallel_map_dict, parallel_map
from .config import config


def sync(src, host, remote_prefix, exclude=['.git*', '.gitignore'], ignore_files=[]):
    remote_prefix = remote_prefix.strip()

    args = ""
    for e in exclude:
        args += f" --exclude={shlex.quote(e)}"

    for i in ignore_files:
        args += f" --filter=':- {i}'"

    if remote_prefix:
        if remote_prefix.startswith("~/"):
            remote_prefix = remote_prefix[2:]
        remote_prefix = shlex.quote(remote_prefix)

    cmd = "rsync -r --delete "+shlex.quote(src)+args+" "+host+":~/"+remote_prefix
    stdout, err = run_process(cmd)

    if err!=0:
        print(stdout)
        print("ERROR: failed to run %s" % cmd)
        return False

    return True


def gather_files_from_host(host, files, dirs, postfix, dest_folder, remote_path):
    host_prefix = host.split(".")[0]

    os.makedirs(dest_folder, exist_ok=True)
    for f in files:
        local_fname = f + ("_" + host_prefix if f in postfix else "")
        dest_file = os.path.join(dest_folder, local_fname)

        path_postfix="/" if f in dirs else ""
        cmd = "rsync -r " + host + ":" + shlex.quote(remote_path + "/" + f) + path_postfix + " '" + dest_file + "'"

        stdout, err = run_process(cmd)
        if err != 0:
            print(stdout)
            print("ERROR: failed to run %s" % cmd)


def run_remote_list(hosts, cmd):
    paths = run_multiple_hosts(hosts, cmd)
    return {k: [a.strip() for a in v[0].split() if a] for k, v in paths.items() if v[1] == 0}


def gather(dest_folder, hosts, remote_path, mode="on_conflict_confirm"):
    res = run_remote_list(hosts, "ls "+shlex.quote(remote_path)+" 2>/dev/null")
    dirs = run_remote_list(hosts, "ls -d " + shlex.quote(remote_path)+"/*/ 2>/dev/null")

    dirs = {k: [os.path.split(os.path.normpath(a))[-1] for a in v if a] for k, v in dirs.items()}
    postfix = {}

    def sync_sequential():
        for host, files in res.items():
            print("Syncing %s" % host)
            gather_files_from_host(host, files, dirs.get(host, []), [], dest_folder, remote_path)

    if mode in ["direct", "on_conflict", "on_conflict_confirm"]:
        error = False
        all_files = {}
        for host, files in res.items():
            for f in files:
                all_files[f] = all_files.get(f, []) + [host]

        for file, hosts in all_files.items():
            if len(hosts) != 1:
                error = True
                if mode == "direct":
                    msg = "ERROR"
                else:
                    msg = "WARNING"
                    for host in hosts:
                        postfix[host] = postfix.get(host, []) + [file]

                print("%s: Conflicting file \"%s\" found on hosts %s" % (msg, file, hosts))

        if error:
            if mode=="on_conflict_confirm":
                inp = input("Conflicting files were found. Host prefix will be appended to them."
                            " Append prefix [a], sync serially [S], or cancel [c]? ")

                if inp.lower() in ["s", ""]:
                    sync_sequential()
                    return True
                elif inp.lower() not in ["a"]:
                    return False
            elif mode=="direct":
                return False
    elif mode == "sequential":
        sync_sequential()
    elif mode == "postfix":
        postfix = res
    else:
        assert False, "Invalid mode: %s" % mode

    parallel_map(res.keys(), lambda t: gather_files_from_host(t, res[t], dirs.get(t,[]), postfix.get(t, []),
                                                              dest_folder, remote_path))
    return True

def gather_relative(folder, hosts, mode="on_conflict_confirm"):
    curr_dir = os.path.relpath(os.path.abspath(folder), os.path.expanduser("~"))
    return gather(folder, hosts, "~/"+curr_dir, mode)

def sync_current_dir(host, remote_prefix=None):
    cwd = os.getcwd()
    copy_this = "../"+os.path.split(cwd)[-1]

    if remote_prefix is None:
        remote_prefix = os.path.relpath(os.path.join(os.getcwd(), ".."), os.path.expanduser("~"))
        if remote_prefix==".":
            remote_prefix = ""

    exclude = config.get("sync", {}).get("exclude", [".git*"])
    blacklists = [".gitignore"] if config.get("sync", {}).get("use_gitignore", True) else []

    sync_list = [(copy_this, remote_prefix)]
    for e in config.get("sync", {}).get("extra", []):
        if e.startswith("~"):
            src_path = os.path.expanduser(e)
            dest_path = e
        else:
            src_path = os.path.join(copy_this, e)
            dest_path = os.path.join(remote_prefix, src_path)

        if os.path.exists(src_path):
            sync_list.append((src_path, dest_path+"/.."))
        else:
            print(f"WARNING: extra sync path {e} doesn't exists")

    for p in sync_list:
        if not sync(p[0], host, p[1], exclude, blacklists):
            print(f"Failed to copy {p[0]} to {host}:{p[1]}. Stopping synchronization...")
            return False

    return True


def sync_curr_dir_multiple(hosts, remote_prefix):
    return parallel_map_dict(hosts, lambda h: sync_current_dir(h, remote_prefix))


def copy_local_dir(hosts=None):
    if hosts is None:
        hosts = config["hosts"]
    res = sync_curr_dir_multiple(hosts, None)
    for m, success in res.items():
        if not success:
            print("Failed to copy data to machine %s" % m)

    return res
