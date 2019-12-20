import threading

def parallel_map(iterator, fn):
    res = []

    def thread_fn(index, data):
        res[index] = fn(data)

    threads = []

    for i in iterator:
        res.append(None)
        t = threading.Thread(target=thread_fn, args=(len(res)-1, i))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    return res

def parallel_map_dict(hosts, fn):
    res = parallel_map(hosts, fn)
    return {k: r for k, r in zip(hosts, res)}
