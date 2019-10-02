import os
import shlex
from process_tools import run_process
from parallel_map import parallel_map_dict


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


def sync_current_dir(host, remote_prefix, exclude='.git*'):
    cwd = os.getcwd()
    copy_this = "../"+os.path.split(cwd)[-1]

    return sync(copy_this, host, remote_prefix, exclude)


def sync_curr_dir_multiple(hosts, remote_prefix, exclude='.git*'):
    return parallel_map_dict(hosts, lambda h: sync_current_dir(h, remote_prefix, exclude))
