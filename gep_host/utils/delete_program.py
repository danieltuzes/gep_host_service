import os
import subprocess
import shutil
import sys
import traceback
from pathlib import Path

import pandas as pd

PROJ_ROOT = Path(os.path.dirname(__file__)).parent.parent.parent


def init_del(program_name: str):
    cmd = f"python {__file__} {program_name}"
    proc = subprocess.run(cmd, shell=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc.returncode, proc.stdout


def delete_program(program_name):
    try:
        # 1. remove program_details.csv
        df = pd.read_csv('programs/program_details.csv', dtype=str)
        df = df[df['program_name'] != program_name]
        df.to_csv('programs/program_details.csv', index=False)

        # 2. remove the folder recursively
        masterfolder = os.path.join(PROJ_ROOT, 'programs', program_name)
        shutil.rmtree(masterfolder)

        # 3. Remove the conda environment
        subprocess.run(f'conda env remove -n {program_name}',
                       shell=True, check=True)
        return 0

    except Exception as e:
        # If there's any error, update status in program_details.csv
        print(f"Error deleting program {program_name}: {e}")
        print(traceback.format_exc())
        put_back = pd.DataFrame({"program_name": [program_name],
                                 "status": ["program uninstall error"]})
        df = pd.concat([df, put_back])
        df.to_csv('programs/program_details.csv', index=False)
        with open(os.path.join(masterfolder, "output_and_error.log"), 'w') as logf:
            print(f"Error deleting program {program_name}: {e}", file=logf)
            print(traceback.format_exc(), file=logf)
        return 1


if __name__ == '__main__':
    # The script expects 3 command-line arguments: program_name, path_to_zip, python_version
    if len(sys.argv) != 2:
        print("Usage: python delete_program.py <program_name>")
        sys.exit(1)

    program_name = sys.argv[1]

    sys.exit(delete_program(program_name))
