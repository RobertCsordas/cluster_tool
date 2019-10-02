import subprocess
from parallel_map import parallel_map_dict

def remote_run(host, command):
    proc = subprocess.Popen(("ssh "+host+" "+command).split(" "), stdout=subprocess.PIPE)
    stdout = proc.communicate()[0].decode()
    return stdout, proc.returncode

def run_multiple_hosts(hosts, command):
    return parallel_map_dict(hosts, lambda h: remote_run(h, command))

def run_multiple_on_multiple(hosts, command):
    def run_commands(host):
        out=[]
        for c in command:
            stdout, err = remote_run(host, c)
            if err!=0:
                print("WARNING: command %s failed on host %s" % (c, host))
                return (out, err)

            out.append(stdout)

        return (out, 0)

    return parallel_map_dict(hosts, run_commands)