import os
import sys
import json

class Config:
    config = {}
    _config_found = False

    files = [os.path.expanduser("~/.cluster.json"), ".cluster.json", "cluster.json"]

    def update_if_available(self, path):
        if os.path.isfile(path):
            self._config_found = True
            with open(path) as json_file:
                self.config.update(json.load(json_file))

    def __init__(self):
        for f in self.files:
            self.update_if_available(f)

        if not self._config_found:
            print("Config file not found. Valid paths: %s" % self.files)
            sys.exit(-1)

    def filter_hosts(self, hosts):
        if hosts is None:
            return

        hosts = hosts.strip()
        invert = hosts[0] in ["!", "~"]
        if invert:
            hosts = hosts[1:]

        hosts = hosts.split(",")

        def any_starts_with(l, s):
            for a in l:
                if s.startswith(a):
                    return True

            return False

        if invert:
            filter_fn = lambda x: not any_starts_with(hosts, x)
        else:
            filter_fn = lambda x: any_starts_with(hosts, x)

        self.config["machines"] = list(filter(filter_fn, self.config["machines"]))
        print("Using hosts: ", " ".join(self.config["machines"]))

    def __getitem__(self, item):
        return self.config[item]

config = Config()
