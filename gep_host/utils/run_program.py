import os
import subprocess
import sys
from pathlib import Path
import traceback
import zipfile

import pandas as pd

PROJ_ROOT = Path(os.path.dirname(__file__)).parent.parent.parent
RUN_DETAILS_CSV = os.path.join(PROJ_ROOT, 'runs', 'run_details.csv')


def zipdir(path, zip_filename):
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(path):
            for file in files:
                zipf.write(os.path.join(root, file),
                           os.path.relpath(os.path.join(root, file),
                                           os.path.join(path, '..')))


def id_row(df, program_name, purpose):
    return ((df['program_name'] == program_name) & (df['purpose'] == purpose))


def init_run(program_name, purpose):
    setup_folder = os.path.join(PROJ_ROOT, 'runs', program_name, purpose)
    cmd = f"python {__file__} {program_name} {purpose}"
    with open(os.path.join(setup_folder, "output_and_error.log"), 'w') as logf:
        proc = subprocess.Popen(cmd, shell=True,
                                cwd=os.path.dirname(__file__),
                                stdout=logf, stderr=logf)

    df = pd.read_csv(RUN_DETAILS_CSV, dtype=str)
    id_row = ((df['program_name'] == program_name) &
              (df['purpose'] == purpose))
    df.loc[id_row, 'PID'] = proc.pid


def run_program(prg_name, purpose):
    code = 0
    try:
        # 1. Update status in run_details.csv
        df = pd.read_csv(RUN_DETAILS_CSV, dtype=str).fillna("")
        df.loc[id_row(df, prg_name, purpose), 'status'] = 'running'
        df.to_csv(RUN_DETAILS_CSV, index=False)

        # 2. clean up the log created during installation
        prg_install_log = os.path.join(PROJ_ROOT,
                                       "programs",
                                       prg_name,
                                       "output_and_error.log")
        if os.path.isfile(prg_install_log):
            os.remove(prg_install_log)

        # 3. Activate the conda environment and run the program
        activate_env_command = f'conda activate {prg_name}'
        args = df.loc[id_row(df, prg_name, purpose), 'python_args'].iloc[0]
        i_cmd = f'{activate_env_command} && python -m {args}'
        setup_folder = os.path.join(PROJ_ROOT, 'runs', prg_name, purpose)
        proc = subprocess.run(i_cmd, shell=True, cwd=setup_folder, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        # 4. compress the whole folder to offer for download
        zip_file = os.path.join(setup_folder,
                                f"{program_name}__{purpose}.zip")
        zipdir(setup_folder, zip_file)

        # 5. Update status in program_details.csv to installed
        if proc.returncode != 0:
            df.loc[id_row(df, prg_name, purpose), 'status'] =\
                'Completed with errors'
            print("Error in the subprocess after calling "
                  f"{i_cmd}: {proc.stdout}")
        else:
            df.loc[id_row(df, prg_name, purpose), 'status'] = 'Completed'
            df.loc[id_row(df, prg_name, purpose) == prg_name,
                   'PID'] = ''
            print(proc.stdout)

    except subprocess.CalledProcessError as err:
        code = 1
        print(f"Error calling subprocess: {err}")
        print(traceback.format_exc())
    except Exception as err:
        code = 2
        print(f"Error in python script: {err}")
        print(traceback.format_exc())
    finally:
        if code != 0:
            df.loc[id_row(df, prg_name, purpose), 'status'] = \
                f'run error, code {code}'
            sys.exit(code)
        df.to_csv(RUN_DETAILS_CSV, index=False)

    sys.exit(0)


if __name__ == '__main__':
    # The script expects 3 command-line arguments: program_name, path_to_zip, python_version
    if len(sys.argv) != 3:
        print("Usage: python run_program.py <program_name> <purpose>")
        sys.exit(1)

    program_name = sys.argv[1]
    purpose = sys.argv[2]

    run_program(program_name, purpose)
    sys.exit(0)
