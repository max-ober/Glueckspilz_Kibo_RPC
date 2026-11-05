#!/usr/bin/env python3
import numpy as np
from copy import deepcopy
from  itertools import combinations
if __name__ == '__main__':
    from random import randint
    from timeit import default_timer as timer

def solve_tsp(p: list[dict], s: dict, t: dict) -> tuple[float, list[int]]:
    all_nodes = deepcopy(p)
    all_nodes.insert(0, s)
    all_nodes.append(t)
    n = len(all_nodes)
    m = create_dist_matrix(all_nodes)

    #Held-Karp
    #heavily modified version of https://github.com/carl-olin/held-karp/blob/master/held-karp.py
    storage = {}
    for k in range(1, n):
        storage[(1 << k, k)] = (m[0, k], 0)
    for step in range(2, n):
        for subset in combinations(range(1, n), step):
            bits = 0
            for b in subset:
                bits |= 1 << b
            for k in subset:
                prev = bits & ~(1 << k)
                re = []
                for d in subset:
                    if d == 0 or d == k: continue
                    re.append((storage[(prev, d)][0] + m[d, k], d))
                storage[(bits, k)] = min(re)
    bits = (2**n - 1) - 1
    res = []
    for k in range(1, n):
        res.append((storage[(bits, k)][0] + m[k, 0], k))
    distance, parent = min(res)
    path = []
    for _ in range(n - 1):
        path.append(parent)
        new_bits = bits & ~(1 << parent)
        _, parent = storage[(bits, parent)]
        bits = new_bits

    path.append(0)
    id_path = []
    for n in list(reversed(path)):
        id_path.append(all_nodes[n]["checkpoint_id"])

    return distance, id_path

def create_dist_matrix(p: list[dict]) -> np.matrix:
    n = len(p)
    m = np.matrix(np.zeros([n, n]))
    for i in range(n):
        for j in range(n):
            if i == j: continue #distance to same point is 0 and we inited the matrix to be 0
            if i == n - 1 and j == 0: continue #make distance from end to start 0 so it has to end there
            else: m[i, j] = dist(p[i], p[j])

    return m

def dist(p1: dict, p2: dict) -> float:
    return np.sqrt((p1["position"][0] - p2["position"][0])**2 + (p1["position"][1] - p2["position"][1])**2 + (p1["position"][2] - p2["position"][2])**2)


if __name__ == '__main__':
    np.set_printoptions(suppress=True, precision=2)
    dummy_data = []

    num_nodes = 12
    s, t = None, None
    for i in range(num_nodes):
        random_pos = [randint(0, 100), randint(0, 100), randint(0, 100)]
        node = {
            "position": random_pos,
            "checkpoint_id": i
        }
        if i == 0: s = node
        elif i == num_nodes - 1: t = node
        else: dummy_data.append(node)

    start = timer()
    if s and t: a, b = solve_tsp(dummy_data, s, t)
    end = timer()
    print(a)
    print(b)
    print(f"Calulated in {end - start} seconds")