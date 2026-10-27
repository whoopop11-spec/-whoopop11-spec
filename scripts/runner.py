#!/usr/bin/env python3
"""Portfolio runner: 4 solver procs per job; first verified SAT wins."""
import os, subprocess, sys, time, signal

cnf_path, job_idx, timeout, out_path = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
nproc = int(os.environ.get("NPROC", "4"))
KISSAT, CADICAL = os.environ.get("KISSAT", "kissat"), os.environ.get("CADICAL", "cadical")

def read_cnf(p):
    n, cls = 0, []
    with open(p) as f:
        for line in f:
            if line.startswith("p"):
                n = int(line.split()[2]); continue
            if not line.strip() or line[0] in "c%":
                continue
            lits = [int(x) for x in line.split()]
            if lits and lits[-1] == 0: lits.pop()
            if lits: cls.append(lits)
    return n, cls

n, clauses = read_cnf(cnf_path)
nae_path = "/tmp/nae.cnf"
with open(nae_path, "w") as f:
    f.write(f"p cnf {n} {2*len(clauses)+1}\n1 0\n")
    for c in clauses:
        f.write(" ".join(map(str, c)) + " 0\n")
        f.write(" ".join(str(-l) for l in c) + " 0\n")

CONFIGS = [
    lambda s: ([KISSAT, "-q", "--sat", f"--seed={s}"], cnf_path),
    lambda s: ([KISSAT, "-q", "--sat", f"--seed={s}"], nae_path),
    lambda s: ([KISSAT, "-q", f"--seed={s}"], nae_path),
    lambda s: ([CADICAL, "-q", "--sat", f"--seed={s}"], nae_path),
    lambda s: ([KISSAT, "-q", "--sat", f"--seed={s}", "--phase=0"], nae_path),
    lambda s: ([KISSAT, "-q", "--sat", f"--seed={s}", "--walkinitially=1", "--walkeffort=1000"], cnf_path),
    lambda s: ([CADICAL, "-q", f"--seed={s}"], cnf_path),
    lambda s: ([KISSAT, "-q", "--sat", f"--seed={s}", "--target=2", "--phase=0"], nae_path),
]

procs = []
for p in range(nproc):
    s = job_idx * nproc + p
    cmd, inp = CONFIGS[s % len(CONFIGS)](s + 1)
    cmd = cmd + [inp]
    log = open(f"/tmp/out_{p}.txt", "w")
    procs.append((subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT), log, " ".join(cmd)))
    print("started", " ".join(cmd), flush=True)

def parse(path):
    vals = {}
    with open(path) as f:
        for line in f:
            if line.startswith("v"):
                for x in line.split()[1:]:
                    v = int(x)
                    if v: vals[abs(v)] = v > 0
    return "".join("1" if vals.get(i, False) else "0" for i in range(1, n + 1))

def verify(a):
    for c in clauses:
        if not any((l > 0) == (a[abs(l) - 1] == "1") for l in c):
            return False
    return True

t0 = time.time(); found = None
while time.time() - t0 < timeout and found is None:
    alive = 0
    for i, (pr, log, desc) in enumerate(procs):
        rc = pr.poll()
        if rc is None:
            alive += 1; continue
        if rc == 10 and found is None:
            log.flush(); a = parse(f"/tmp/out_{i}.txt")
            if verify(a):
                found = (a, desc)
            else:
                print("BAD witness from", desc, flush=True)
            procs[i] = (pr, log, desc + " [done]")
    if alive == 0 and found is None:
        break
    time.sleep(0.2)

for pr, _, _ in procs:
    if pr.poll() is None:
        pr.kill()
if found:
    open(out_path, "w").write(found[0])
    print(f"SAT in {time.time()-t0:.1f}s by {found[1]}", flush=True)
    open(out_path + ".who", "w").write(f"job {job_idx} {time.time()-t0:.1f}s {found[1]}\n")
    sys.exit(0)
print(f"no solution after {time.time()-t0:.1f}s", flush=True)
sys.exit(1)
