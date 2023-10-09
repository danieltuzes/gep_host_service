import os
import subprocess
import zipfile
import json
import sys
import datetime
from configparser import ConfigParser, ExtendedInterpolation
from typing import Union
import traceback

import pandas as pd
from flask import current_app


def init_install(program_name,
                 program_zip_path,
                 python_version,
                 selected_libs,
                 def_args) -> Union[int, str]:
    # Check uniqueness of program name
    if os.path.exists(current_app.config["PRG"]):
        df = pd.read_csv(current_app.config["PRG"], dtype=str)
        if program_name in df['program_name'].values:
            os.remove(program_zip_path)
            return 'Program upload unsuccessful due to non-unique name.'

    # trigger the installation
    selected_libs_str = ", ".join(selected_libs)
    masterfolder = os.path.join(current_app.config["PRGR"], program_name)
    os.makedirs(masterfolder)
    cmd = (f"python {__file__} {program_name} {program_zip_path} "
           f'{python_version} "{selected_libs_str}"')
    with open(os.path.join(masterfolder, "install_output_and_error.log"), 'w') as logf:
        proc = subprocess.Popen(cmd, shell=True,  stdout=logf, stderr=logf)

    # Update program details CSV
    new_entry = pd.DataFrame({
        'program_name': [program_name],
        'upload_date': [datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        'python_version': [python_version],
        'status': ['installing'],
        'PID': [proc.pid],
        'zip_fname': [program_zip_path],
        'selected_libs': [selected_libs_str],
        'def_args': [def_args],
        'inputs': json.dumps({}),
        'outputs': json.dumps({})
    })
    if os.path.exists(current_app.config["PRG"]):
        df = pd.concat([df, new_entry], ignore_index=True)
    else:
        df = new_entry
    df.to_csv(current_app.config["PRG"], index=False)

    return 0


def run_and_verify(cmd: str, cwd=None):
    print(cmd)
    proc = subprocess.run(cmd, cwd=cwd, shell=True, text=True,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    print(proc.stdout)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(returncode=proc.returncode,
                                            cmd=cmd, stderr=proc.stdout)


def install_program(program_name,
                    program_zip_name,
                    required_python_version,
                    required_libs_raw: str):
    from set_conf import set_conf
    app_conf = {}
    set_conf(app_conf)

    code = 0
    try:
        # 1. Update status in program_details.csv
        df = pd.read_csv(app_conf["PRG"], dtype=str)
        df.loc[df['program_name'] == program_name, 'status'] = 'extracting'
        df.to_csv(app_conf["PRG"], index=False)

        # 2. Extract zip to the masterfolder
        zipf = os.path.join(app_conf["PRGR"], program_zip_name)
        masterfolder = os.path.join(app_conf["PRGR"], program_name)
        with zipfile.ZipFile(zipf, 'r') as zip_ref:
            zip_ref.extractall(masterfolder)

        # 3. Read and update the MasterConfig.cfg file
        config_file = os.path.join(masterfolder, 'config', 'MasterConfig.cfg')
        inputs = {}
        outputs = {}
        if os.path.isfile(config_file):
            config = ConfigParser(
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
                        inputs[option] = rel_ifile
                    else:
                        inputs[option] = None

            # get the expected outputs
            if config.has_section("outputs"):
                for option in config.options("outputs"):
                    ofile = config.get("outputs", option)
                    rel_ofile = os.path.relpath(ofile, masterfolder)
                    if rel_ofile.startswith(".."):
                        print("Error: output file shouldn't be saved "
                              "above package level. "
                              "Please delete the package and re-upload it.")
                        code = 3
                    outputs[option] = rel_ofile

        df = pd.read_csv(app_conf["PRG"], dtype=str)
        df.loc[df['program_name'] == program_name,
               'inputs'] = json.dumps(inputs)
        df.loc[df['program_name'] == program_name,
               'outputs'] = json.dumps(outputs)

        # 4. Create a new conda environment with the provided python version
        df.loc[df['program_name'] == program_name,
               'status'] = 'creating conda env'
        df.to_csv(app_conf["PRG"], index=False)
        c_cmd = f'conda create -y -n {program_name} python={required_python_version} conda-build'
        run_and_verify(c_cmd)

        # 4. Activate the new conda environment and install the program using pip
        df = pd.read_csv(app_conf["PRG"], dtype=str)
        df.loc[df['program_name'] == program_name,
               'status'] = 'installing packages'
        df.to_csv(app_conf["PRG"], index=False)
        activate_env_command = f'{app_conf["activate"]}{program_name}'
        if os.path.isfile(os.path.join(masterfolder, "setup.py")):
            print("setup.py is found")
            pip_install_command = ' && pip install .'
        elif os.path.join(masterfolder, "requirements.txt"):
            print("requirements.txt is found")
            pip_install_command = ' && pip install -r requirements.txt'
        else:
            pip_install_command = ""
        i_cmd = f'{activate_env_command} {pip_install_command}'
        run_and_verify(i_cmd, cwd=masterfolder)

        # 5. add the libraries
        required_libs = required_libs_raw.split(", ")
        if len(required_libs) > 0 and os.path.isfile(app_conf["LIB"]):
            libs = pd.read_csv(app_conf["LIB"])
            conda_devs = [f'{app_conf["activate"]}{program_name}']
            for lib in libs.itertuples():
                if lib.library_name not in required_libs:
                    continue
                path = os.path.join(app_conf["LIBR"],
                                    lib.library_name,
                                    lib.path_to_exec)
                conda_devs.append(f'conda develop "{path}"')

                used_in_raw = lib.used_in
                used_in = json.loads(used_in_raw)
                used_in.append(program_name)
                used_in_raw = json.dumps(used_in)
                libs.loc[libs["library_name"] ==
                         lib.library_name, "used_in"] = used_in_raw
            libs.to_csv(app_conf["LIB"], index=False)
            cmd = " && ".join(conda_devs)
            run_and_verify(cmd, cwd=masterfolder)

        # 6. Update status in program_details.csv to installed
        df = pd.read_csv(app_conf["PRG"], dtype=str)
        df.loc[df['program_name'] == program_name, 'status'] = 'Installed'
        df.loc[df['program_name'] == program_name, 'PID'] = ''

    except subprocess.CalledProcessError as err:
        code = 1
        print(f"Error calling subprocess:", traceback.format_exc(), sep="\n")
    except Exception:
        code = 2
        print(f"Error in python script.", traceback.format_exc(), sep="\n")
    finally:
        if code != 0:
            df = pd.read_csv(app_conf["PRG"], dtype=str)
            df.loc[df['program_name'] == program_name, 'status'] =\
                f'Installed with error ({code})'
        df.to_csv(app_conf["PRG"], index=False)


if __name__ == '__main__':
    if len(sys.argv) not in [4, 5]:
        print("Usage: python install_program.py",
              "<program_name> <zip_filename>",
              "<python_version> ['<required_lib1>, <required_lib2>']")
        print("While program is called as:\n", sys.argv)
        sys.exit(1)

    program_name = sys.argv[1]
    program_zip_name = sys.argv[2]
    required_python_version = sys.argv[3]

    required_libs_str = "''"
    if len(sys.argv) == 5:
        required_libs_str = sys.argv[4]

    install_program(program_name,
                    program_zip_name,
                    required_python_version,
                    required_libs_str)
    sys.exit(0)
