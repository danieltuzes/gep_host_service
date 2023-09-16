import os
import subprocess
import zipfile
import json
import sys
import datetime
from configparser import ConfigParser, ExtendedInterpolation
from pathlib import Path
from typing import Union
import traceback

import pandas as pd

PROJ_ROOT = Path(os.path.dirname(__file__)).parent.parent.parent
PROGRAM_DETAILS_CSV = os.path.join(PROJ_ROOT,
                                   'programs/program_details.csv')


def init_install(program_name, program_zip_path, python_version) -> Union[int, str]:
    # Check uniqueness of program name
    if os.path.exists(PROGRAM_DETAILS_CSV):
        df = pd.read_csv(PROGRAM_DETAILS_CSV, dtype=str)
        if program_name in df['program_name'].values:
            os.remove(program_zip_path)
            return 'Program upload unsuccessful due to non-unique name.'

    masterfolder = os.path.join(PROJ_ROOT, 'programs', program_name)
    os.makedirs(masterfolder)
    cmd = f"python {__file__} {program_name} {program_zip_path} {python_version}"
    with open(os.path.join(masterfolder, "output_and_error.log"), 'w') as logf:
        proc = subprocess.Popen(cmd, shell=True,  stdout=logf, stderr=logf)

    # Update program details CSV
    new_entry = pd.DataFrame({
        'program_name': [program_name],
        'upload_date': [datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        'python_version': [python_version],
        'status': ['installing'],
        'PID': [proc.pid],
        'zip_fname': program_zip_path,
    })
    if os.path.exists(PROGRAM_DETAILS_CSV):
        df = pd.concat([df, new_entry], ignore_index=True)
    else:
        df = new_entry
    df.to_csv(PROGRAM_DETAILS_CSV, index=False)

    return 0


def install_program(program_name, program_zip_path, required_python_version):
    code = 0
    try:
        # 1. Update status in program_details.csv
        df = pd.read_csv(PROGRAM_DETAILS_CSV, dtype=str)
        df.loc[df['program_name'] == program_name, 'status'] = 'extracting'
        df.to_csv(PROGRAM_DETAILS_CSV, index=False)

        # 2. Extract zip to the masterfolder
        zipf = os.path.join(PROJ_ROOT, 'programs', program_zip_path)
        masterfolder = os.path.join(PROJ_ROOT, 'programs', program_name)
        with zipfile.ZipFile(zipf, 'r') as zip_ref:
            zip_ref.extractall(masterfolder)
        os.remove(zipf)

        # 3. Read and update the MasterConfig.cfg file
        config_file = os.path.join(masterfolder, 'config', 'MasterConfig.cfg')
        inputs = []
        outputs = []
        if os.path.isfile(config_file):
            config = ConfigParser(os.environ,
                                  interpolation=ExtendedInterpolation())
            config.read(config_file)
            if 'Root' in config and 'RootDir' in config['Root']:
                config.set('Root', 'RootDir', masterfolder)
                with open(config_file, 'w') as configfile:
                    config["DEFAULT"] = {}
                    config.write(configfile)

            # get the list of existing input files
            if config.has_section("inputs"):
                for option in config.options("inputs"):
                    ifile = config.get("inputs", option)
                    if os.path.isfile(ifile):
                        rel_ifile = os.path.relpath(ifile, masterfolder)
                        inputs.append((option, rel_ifile))
                    else:
                        inputs.append((option, None))

            # get the expected outputs
            if config.has_section("outputs"):
                for option in config.options("outputs"):
                    ofile = config.get("outputs", option)
                    rel_ofile = os.path.relpath(ofile, masterfolder)
                    if rel_ofile.startswith(".."):
                        print("Error: output file shouldn't be saved"
                              "above package level."
                              "Please delete the package and re-upload it.")
                        code = 3
                    outputs.append((option, rel_ofile))

        df.loc[df['program_name'] == program_name,
               'inputs'] = json.dumps(inputs)
        df.loc[df['program_name'] == program_name,
               'outputs'] = json.dumps(outputs)

        # 4. Create a new conda environment with the provided python version
        df.loc[df['program_name'] == program_name,
               'status'] = 'creating conda env'
        df.to_csv(PROGRAM_DETAILS_CSV, index=False)
        c_cmd = f'conda create -y -n {program_name} python={required_python_version} conda-build'
        subprocess.run(c_cmd, capture_output=True,
                       shell=True, check=True)

        # 4. Activate the new conda environment and install the program using pip
        df.loc[df['program_name'] == program_name,
               'status'] = 'installing packages'
        df.to_csv(PROGRAM_DETAILS_CSV, index=False)
        activate_env_command = f'conda activate {program_name}'
        pip_install_command = 'pip install .'
        i_cmd = f'{activate_env_command} && {pip_install_command}'
        subprocess.run(i_cmd, capture_output=True,
                       shell=True, cwd=masterfolder)

        # 5. Update status in program_details.csv to installed
        df.loc[df['program_name'] == program_name, 'status'] = 'installed'
        df.loc[df['program_name'] == program_name, 'PID'] = ''

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
            df.loc[df['program_name'] == program_name, 'status'] =\
                f'install error code {code}'
        df.to_csv(PROGRAM_DETAILS_CSV, index=False)

    sys.exit(code)


if __name__ == '__main__':
    # The script expects 3 command-line arguments: program_name, path_to_zip, python_version
    if len(sys.argv) != 4:
        print(
            "Usage: python install_program.py <program_name> <path_to_zip> <python_version>")
        sys.exit(1)

    program_name = sys.argv[1]
    program_zip_path = sys.argv[2]
    required_python_version = sys.argv[3]

    install_program(program_name, program_zip_path, required_python_version)
    sys.exit(0)
