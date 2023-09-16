import os
import subprocess
import shutil
import sys
from pathlib import Path
import traceback

import pandas as pd

PROJ_ROOT = Path(os.path.dirname(__file__)).parent.parent.parent
RUN_DETAILS_CSV = os.path.join(PROJ_ROOT, 'runs/run_details.csv')


def init_del(program_name: str, purpose: str):
    cmd = f"python {__file__} {program_name} {purpose}"
    proc = subprocess.run(cmd, shell=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc.returncode, proc.stdout


def delete_run(program_name: str, purpose: str):
    try:
        # 1. remove run_details.csv
        df = pd.read_csv(RUN_DETAILS_CSV, dtype=str)
        df = df[~((df['program_name'] == program_name)
                & (df['purpose'] == purpose))]
        df.to_csv(RUN_DETAILS_CSV, index=False)

        # 2. remove the folder recursively
        setup_folder = os.path.join(PROJ_ROOT,
                                    'runs',
                                    program_name,
                                    purpose)
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
                                 "status": ["run delete error"]})
        df = pd.concat([df, put_back])
        df.to_csv(RUN_DETAILS_CSV, index=False)
        return 2


if __name__ == '__main__':
    # The script expects 3 command-line arguments: program_name, path_to_zip, python_version
    if len(sys.argv) != 3:
        print("Usage: python delete_run.py <program_name> <purpose>")
        sys.exit(1)

    program_name = sys.argv[1]
    purpose = sys.argv[2]

    sys.exit(delete_run(program_name, purpose))
