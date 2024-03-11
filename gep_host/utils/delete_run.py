import os
import subprocess
import shutil
import sys
import traceback

import pandas as pd
from flask import current_app


def init_del(program_name: str, purpose: str):
    cmd = f"python {__file__} {current_app.config['masterconf_path']} {program_name} {purpose}"
    proc = subprocess.run(cmd, shell=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc.returncode, proc.stdout


def delete_run(masterconf_path: str, program_name: str, purpose: str):
    from helpers import remove_readonly, remove_val_from_json
    """Deletes a run.

    Parameters
    ----------
    masterconf_path : str
        Path to the master configuration file.
    program_name : str
        The program name for which the run was made.
    purpose : str
        The purpose used for the run.
    """
    # the price of using the same file where the deletion is initiated from python
    # and where the console script's deletion is implemented
    from set_conf_init import set_conf
    config = {}
    set_conf(config, masterconf_path)

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

        # Check if the parent folder (program folder) is empty
        program_folder = os.path.join(config["RUNR"], program_name)
        if not os.listdir(program_folder):  # Check if the folder is empty
            os.rmdir(program_folder)  # Remove the empty folder
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
    if len(sys.argv) != 4:
        print("Usage: python delete_run.py <masterconf_path> <program_name> <purpose>")
        sys.exit(1)

    masterconf_path = sys.argv[1]
    program_name = sys.argv[2]
    purpose = sys.argv[3]

    sys.exit(delete_run(masterconf_path, program_name, purpose))
