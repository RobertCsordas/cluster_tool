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

def gather_files_from_host(host, files, dest_folder, remote_path):
    host_prefix = host.split(".")[0]


    assert False
    for f in files:
        dest_file = os.path.join(dest_folder, f + "_" + host_prefix)
        cmd = "rsync -r " + host + ":" + shlex.quote(remote_path + "/" + f) + " '" + dest_file + "'"

        print(cmd)
        stdout, err = run_process(cmd)
        if err != 0:
            print(stdout)
            print("ERROR: failed to run %s" % cmd)

def run_remote_list(hosts, cmd):
    paths = run_multiple_hosts(hosts, cmd)
    return [(k, [a.strip() for a in v[0].split() if a]) for k, v in paths.items() if v[1] == 0]

def gather(dest_folder, hosts, remote_path):
    res = run_remote_list(hosts, "ls "+shlex.quote(remote_path))
    print(res)
    dirs = run_remote_list(hosts, "ls -d " + shlex.quote(remote_path)+"/*/")


    print (dirs)

    #parallel_map(res, lambda t: gather_files_from_host(t[0], t[1], dest_folder, remote_path))


def sync_current_dir(host, remote_prefix, exclude='.git*'):
    cwd = os.getcwd()
    copy_this = "../"+os.path.split(cwd)[-1]

    return sync(copy_this, host, remote_prefix, exclude)


def sync_curr_dir_multiple(hosts, remote_prefix, exclude='.git*'):
    return parallel_map_dict(hosts, lambda h: sync_current_dir(h, remote_prefix, exclude))
