import os
import shlex
from process_tools import run_process, run_multiple_hosts
from parallel_map import parallel_map_dict, parallel_map


def sync(src, host, remote_prefix, exclude='.git*'):
    gitignore_file = os.path.join(src, ".gitignore")
    filt_arg = ""
    if os.path.isfile(gitignore_file):
        filt_arg = "--filter=':- "+gitignore_file+"'"

    remote_prefix = remote_prefix.strip()

    cmd = "rsync -r "+shlex.quote(src)+" --exclude='"+exclude+"' "+filt_arg+" "+host+":~/"+(
            shlex.quote(remote_prefix) if remote_prefix else "")
    stdout, err = run_process(cmd)

    if err!=0:
        print(stdout)
        print("ERROR: failed to run %s" % cmd)
        return False

    return True


def gather_files_from_host(host, files, dirs, postfix, dest_folder, remote_path):
    host_prefix = host.split(".")[0]

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
                            " Do you want to countinue [Y,n]? ")

                if inp.lower() not in ["y", "", "yes"]:
                    return False
            elif mode=="direct":
                return False

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

def sync_current_dir(host, remote_prefix=None, exclude='.git*'):
    cwd = os.getcwd()
    copy_this = "../"+os.path.split(cwd)[-1]

    if remote_prefix is None:
        remote_prefix = os.path.relpath(os.path.join(os.getcwd(), ".."), os.path.expanduser("~"))
        if remote_prefix==".":
            remote_prefix = ""

    return sync(copy_this, host, remote_prefix, exclude)


def sync_curr_dir_multiple(hosts, remote_prefix, exclude='.git*'):
    return parallel_map_dict(hosts, lambda h: sync_current_dir(h, remote_prefix, exclude))
