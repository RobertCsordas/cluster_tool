import os
import sys
import json
from typing import Dict, List, Set, Any


def recursive_update_dict(dest: Dict, src: Dict, append_lists: Set[str] = {}) -> Dict:
    def do_update(dest: Dict, src: Dict, current: str):
        res = dest.copy()
        for k, v in src.items():
            full_name = f"{current}/{k}" if current else k
            if isinstance(v, dict) and isinstance(res.get(k), dict):
                res[k] = do_update(res[k], v, full_name)
            elif isinstance(v, list) and full_name in append_lists:
                res[k] = v + dest[k]
            else:
                res[k] = v
        return res
    return do_update(dest, src, "")


class Config:
    config = {}
    _config_found = False
    gpu_filter = {}

    files = [os.path.expanduser("~/.cluster.json"), ".cluster.json", "cluster.json"]

    def update_if_available(self, path):
        if os.path.isfile(path):
            self._config_found = True
            with open(path) as json_file:
                try:
                    self.config = recursive_update_dict(self.config, json.load(json_file),
                                                        {"sync/exclude"})
                except:
                    print(f"Error while loading file {path}:")
                    raise

    def __init__(self):
        self.slurm_enabled = False
        self.slurm_machine_whitelist = None
        self.enabled_gpu_types = None
        self.slurm_partition = None
        for f in self.files:
            self.update_if_available(f)

        if not self._config_found:
            print("Config file not found. Valid paths: %s" % self.files)
            sys.exit(-1)

    def set_slurm(self, enabled: bool):
        self.slurm_enabled = enabled

    def set_gpu_type(self, typelist: str):
        typelist = typelist.strip()
        if typelist:
            typelist = typelist.split(",")
            self.enabled_gpu_types = {t.lower() for t in typelist}
        else:
            self.enabled_gpu_types = None

    def set_slurm_partition(self, partition: str):
        partition = partition.strip()
        self.slurm_partition = partition if partition else None

    def set_args(self, args):
        self.set_slurm(args.slurm)
        self.filter_hosts(args.hosts)
        self.set_gpu_type(args.gpu_type)
        self.set_slurm_partition(args.slurm_partition)
        self.num_cpus = args.num_cpus if args.num_cpus else None
        self.memory = args.memory if args.memory else None

    def create_gpu_filters(self, host_list: List[str]):
        res_hosts = []
        gpu_allow = {}

        for h_orig in host_list:
            h = h_orig.strip()
            h = h.split("{")
            assert len(h) in [1,2], f"Invalid GPU list specification: {h_orig}"

            host = self.get_full_hostname(h[0].strip())
            assert len(host) > 0, f"No hostnames match {h[0]}"
            assert len(host) <= 1, f"Multiple hostnames match {h[0]}: {host}"
            host = host[0]

            res_hosts.append(host)

            if len(h)==2:
                assert h[1].endswith("}"), f"Invalid GPU list specification: {h_orig}"
                gpus = h[1].strip()[:-1].split(";")
                gpu_allow[host] = []
                for g in gpus:
                    g = g.split("-")
                    if len(g)==1:
                        gpu_allow[host].append(int(g[0]))
                    elif len(g)==2:
                        for a in range(int(g[0]), int(g[1])+1):
                            gpu_allow[host].append(a)
                    else:
                        assert False, f"Invalid GPU list specification: {h_orig}"

        return res_hosts, gpu_allow

    def filter_gpus_host(self, host: str, gpus: List[int]) -> List[int]:
        gpus = [i for i in gpus if (host not in self.gpu_filter or i in self.gpu_filter.get(host))]
        return self.filter_blacklisted_gpus(host, gpus)

    def filter_gpus(self, host_dict = Dict[str, List[int]]) -> Dict[str, List[int]]:
        if not self.gpu_filter:
            return host_dict

        return {k: self.filter_hosts(k, v) for k, v in host_dict.items()}

    def filter_hosts(self, hosts):
        if hosts is None:
            return

        hosts = hosts.strip()
        invert = hosts[0] in ["!", "~"]
        if invert:
            hosts = hosts[1:]

        hosts = hosts.split(",")
        hosts, gpu_allow = self.create_gpu_filters(hosts)

        if gpu_allow:
            assert not invert, "GPU filter is allowed only in non-inverting mode"
            self.gpu_filter = gpu_allow

        def any_starts_with(l, s):
            for a in l:
                if s.startswith(a):
                    return True

            return False

        if invert:
            filter_fn = lambda x: not any_starts_with(hosts, x)
        else:
            filter_fn = lambda x: any_starts_with(hosts, x)

        self.config["hosts"] = list(filter(filter_fn, self.config.get("hosts",[])))
        if "slurm" in self.config:
            self.config["slurm"] = {k: v for k, v in self.config["slurm"].items() if filter_fn(k)}

        print("Using hosts: ", " ".join(self.config["hosts"]))

    def get_env(self, host):
        envs = self.config.get("envs", {})
        return envs.get(host, envs.get("all", ""))

    def get_command(self, host, command, default=None):
        if default is None:
            default = command
        commands = self.config.get("commands", {})
        return commands.get(host, commands.get("all", {})).get(command, default)

    def filter_blacklisted_gpus(self, host, gpu_id_list):
        blacklist = set(int(i) for i in self.config.get("gpu_blacklist", {}).get(host, []))
        return [g for g in gpu_id_list if int(g) not in blacklist]
    
    def set_slurm_machine_whitelist(self, host, machines):
        if not machines:
            return 
        
        if self.slurm_machine_whitelist is None:
            self.slurm_machine_whitelist = {}
        
        if host not in self.slurm_machine_whitelist:
            self.slurm_machine_whitelist[host] = set()

        self.slurm_machine_whitelist[host].update(machines)
            

    def get_full_hostname(self, beginning):
        res = []
        for h in self.config.get("hosts", []):
            if h.startswith(beginning):
                res.append(h)

        for h in self.get("slurm", {}).keys():
            machines = self.config["slurm"][h].get("machines", [])
            if h.startswith(beginning):
                self.set_slurm_machine_whitelist(h, machines)
                res.append(h)

            for m in machines:
                if m.lower().startswith(beginning):
                    self.set_slurm_machine_whitelist(h, {m})
                    res.append(h)                   

        res = list(set(res))
        return res

    def __getitem__(self, item):
        return self.config[item]

    def get(self, item, default=None):
        return self.config.get(item, default)

    def update(self, cfg: Dict[str, Any]):
        def u(target, src):
            for k, v in src.items():
                old = target.get(k)
                if isinstance(old, dict):
                    u(old, v)
                else:
                    target[k] = v
        u(self.config, cfg)

    def get_all_hosts(self) -> List[str]:
        res = self["hosts"]
        if self.slurm_enabled:
            res = res + list(self.get("slurm", {}).keys())
        return res

    def get_wandb_env(self) -> str:
        wandb = self.get("wandb", {}).get("apikey")
        if wandb is None:
            wandb = ""
        else:
            wandb = " WANDB_API_KEY=" + wandb + " "
        return wandb

    def get_ssh_flags(self, hostname) -> str:
        ssh_cfg = self.get("host_config", {}).get(hostname, {})
        res = ""
        if "user" in ssh_cfg:
            res += f" -l {ssh_cfg['user']}"
        
        if "key" in ssh_cfg:
            res += f" -i {ssh_cfg['key']}"

        if res:
            res += " "
        
        return res
    
    def is_local_run(self, host: str) -> bool:
        for h, path in self.config.get("nosync_if_exists",{}).items():
            if host.startswith(h) and os.path.exists(path):
                return True
        
        return False


config = Config()
