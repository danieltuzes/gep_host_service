import os
import subprocess
import shutil
import sys
import traceback

import pandas as pd
from flask import current_app


def init_del(program_name: str, purpose: str):
    cmd = f"python {__file__} {program_name} {purpose}"
    proc = subprocess.run(cmd, shell=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc.returncode, proc.stdout


def delete_run(program_name: str, purpose: str):
    from helpers import remove_readonly, remove_val_from_json
    """Deletes a run.

    Parameters
    ----------
    program_name : str
        The program name for which the run was made.
    purpose : str
        The purpose used for the run.
    """
    # the price of using the same file where the deletion is initiated from python
    # and where the console script's deletion is implemented
    from set_conf import set_conf
    config = {}
    set_conf(config)

    try:
        files = pd.read_csv(config["FLE"], dtype=str)
        # Unregister files
        runid = f"{program_name}__{purpose}"
        files["used_in"] = files["used_in"].apply(remove_val_from_json,
                                                  val_2_remove=runid)
        files.to_csv(config["FLE"], index=False)

        # 1. remove run_details.csv
        df = pd.read_csv(config["RUN"], dtype=str)
        df = df[~((df['program_name'] == program_name)
                & (df['purpose'] == purpose))]
        df.to_csv(config["RUN"], index=False)

        # 2. remove the folder recursively
        setup_folder = os.path.join(config["RUNR"],
                                    program_name,
                                    purpose)
        remove_readonly(setup_folder)
        shutil.rmtree(setup_folder)
        return 0

    except FileNotFoundError as e:
        print("Error deleting program",
              f"{program_name} with purpose {purpose}: {e}")
        print(traceback.format_exc())
        return 1
    except Exception as e:
        # If there's any error, update status in run_details.csv
        print("Error deleting program",
              f"{program_name} with purpose {purpose}: {e}")
        print(traceback.format_exc())
        put_back = pd.DataFrame({"program_name": [program_name],
                                 "purpose": [purpose],
                                 "status": ["Completed (run delete error)"]})
        df = pd.concat([df, put_back])
        df.to_csv(config["RUN"], index=False)
        return 2


if __name__ == '__main__':
    # The script expects 3 command-line arguments: program_name, path_to_zip, python_version
    if len(sys.argv) != 3:
        print("Usage: python delete_run.py <program_name> <purpose>")
        sys.exit(1)

    program_name = sys.argv[1]
    purpose = sys.argv[2]

    sys.exit(delete_run(program_name, purpose))
