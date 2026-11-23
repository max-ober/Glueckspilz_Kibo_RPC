import argparse
from pathlib import Path
from subprocess import Popen, PIPE, STDOUT
import json
from pprint import pprint
from time import time 

def run(args):
    if not args.simulator:
        print("The root directory of the simulator needs to be defined using: python3 tester.py -s [path_to_simulator]")
        return

    simulatorFile = Path(f"{args.simulator}/simulation.sh")
    logsFolder = Path(f"{args.simulator}/share/logs")

    if not simulatorFile.is_file():
        print("Could not find simulation.sh")
        return

    if not logsFolder.is_dir():
        print("Could not find the logs directory")
        return

    sim_results = []

    n = int(args.iterations)
    for i in range(n):
        print(f"Starting Simulator instance {i}")
        process = Popen(f"{args.simulator}/simulation.sh", shell=True, stdout=PIPE, stderr=STDOUT, cwd=args.simulator)
        if process.stdout:
            with process.stdout:
                log_subprocess_output(process.stdout, i)
        exitcode = process.wait()
        print(f"Simulator finished with exit code {exitcode}")
        if exitcode != 0: return

        # read results
        with open(f"{args.simulator}/share/logs/latest/judge_module_logs/result.json") as f:
            sim_results.append(json.load(f))

    total_duration = 0
    finished_count = 0
    total_cp_count = 0
    total_cp_success_count = 0
    total_cp_lvl = 0
    for r in sim_results:
        if not r["Illegal"]:
            repo = r["JudgeReport"]
            if repo["mission"]["finished"]:
                finished_count += 1
                total_duration += repo["mission"]["duration_sec"]
            for cp in repo["checkpoint_detail"]:
                total_cp_count += 1
                if cp["success"]:
                    total_cp_success_count += 1
                    total_cp_lvl += cp["level"]

        pprint(r)

    avg_cp_lvl = total_cp_lvl / total_cp_success_count
    avg_duration = total_duration / n

    report = f'''Simulations run: {n}
    Finished {finished_count} of those successfully
    Average time (for successfull missions): {avg_duration}
    Passed {total_cp_success_count} out of {total_cp_count} Checkpoints
    Average Checkpoint level: {avg_cp_lvl}
    '''
    pprint(report)
    with open(f"report_{int(time())}.txt", "+w", encoding="utf-8") as f:
        f.write(report)
        f.write("=== Raw results === \n")
        for i in range(len(sim_results)):
            f.write(f"Sim {i}: {sim_results[i]}\n")


    


    
def log_subprocess_output(pipe, i):
    for line in iter(pipe.readline, b''):
        print(f"Simulator {i}: {line}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Runs the Simulator x times and collects the results")
    parser.add_argument("-i", "--iterations", help="Number of simulator iterations", default=10)
    parser.add_argument("-s", "--simulator", help="Root directory of the simulator to use")
    #parser.add_argument("-p", "--processes", help="Number of simulator processes to spawn at a time", default=1)
    args = parser.parse_args()
    run(args)