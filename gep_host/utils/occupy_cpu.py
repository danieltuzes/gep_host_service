
"""This script is used to occupy CPU resources for testing purposes.
It starts multiple processes, each performing a CPU-intensive task.
The processes run for a specified amount of time and then terminate.
"""

import multiprocessing
import time


def cpu_intensive_task():
    while True:
        _ = [x**2 for x in range(10000)]


if __name__ == "__main__":

    # Determine the number of cores and start a process for each core
    num_cores = multiprocessing.cpu_count() // 2 + 4

    processes = []
    for _ in range(num_cores):
        p = multiprocessing.Process(target=cpu_intensive_task)
        p.start()
        processes.append(p)

    # Run for a specified amount of time
    time_to_run = 100  # run for 100 seconds
    time.sleep(time_to_run)

    # Terminate the processes
    for p in processes:
        p.terminate()
        p.join()

    print(f"Completed running for {time_to_run} seconds")
