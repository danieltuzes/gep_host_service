import os
import subprocess
import shutil
import sys
import traceback
import pandas as pd

from flask import current_app


def run_and_verify(cmd: str, cwd=None):
    proc = subprocess.run(cmd, cwd=cwd, shell=True, text=True,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(returncode=proc.returncode,
                                            cmd=cmd, stderr=proc.stdout)


def init_del(program_name: str):

    cmd = f"python {__file__} {current_app.config['masterconf_path']} {program_name}"
    proc = subprocess.run(cmd, shell=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout


def delete_program(masterconf_path: str, program_name: str):
    """Delete a program.

    Parameters
    ----------
    masterconf_path : str
        Path to the master configuration file.
        Needed 
    program_name : str
        Delete this program and its zip file.

    """
    # the price of using the same file where the deletion is initiated from python
    # and where the console script's deletion is implemented
    from gep_host.utils.set_conf_init import set_conf
    from helpers import remove_readonly, remove_val_from_json
    config = {}
    set_conf(config, masterconf_path)

    code = 0
    try:
        masterfolder = os.path.join(config["PRGR"], program_name)
        # 1. remove program_details.csv and get the zip_fname
        df = pd.read_csv(config["PRG"], dtype=str)
        zip_fname = df.loc[df['program_name'] ==
                           program_name, "zip_fname"].iloc[0]
        df = df[df['program_name'] != program_name]
        df.to_csv(config["PRG"], index=False)

        # 2. remove the folder recursively
        if zip_fname != zip_fname:
            print("Program package file is not associated with the program.")
        else:
            zip_path = os.path.join(config["PRGR"], zip_fname)
            if os.path.isfile(zip_path):
                os.remove(zip_path)
            else:
                print("The package zip file has been already deleted.")

        if os.path.isdir(masterfolder):
            remove_readonly(masterfolder)
            shutil.rmtree(masterfolder)
        else:
            print("The program folder has been already deleted.")
            code = 2

        # 3. Remove the conda environment
        cmd = f'conda env remove -n {program_name}'
        run_and_verify(cmd)

        libs = pd.read_csv(config["LIB"])
        libs["used_in"] = libs["used_in"].apply(remove_val_from_json,
                                                val_2_remove=program_name)
        libs.to_csv(config["LIB"], index=False)

        return code

    except subprocess.CalledProcessError as err:
        code = 1

        print(f"Error deleting program:", traceback.format_exc(), sep="\n")
        print(f"Standard error:", err.stderr, sep="\n")
    except Exception as e:
        code = 2
        # If there's any error, update status in program_details.csv
        print(f"Error deleting program {program_name}: {e}")
        print(traceback.format_exc())
        put_back = pd.DataFrame({"program_name": [program_name],
                                 "status": ["Installed (deleting with error)"]})
        df = pd.concat([df, put_back])
        df.to_csv(config["PRG"], index=False)
        if os.path.isdir(masterfolder):
            with open(os.path.join(masterfolder, "install_output_and_error.log"), 'a') as logf:
                print(f"Error deleting program {program_name}: {e}", file=logf)
                print(traceback.format_exc(), file=logf)
        else:
            print(f"masterfolder {masterfolder} has been already deleted,",
                  "no log file is created.")
        return 1


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python delete_program.py <masterconf_path> <program_name>")
        sys.exit(1)

    masterconf_path = sys.argv[1]
    program_name = sys.argv[2]

    sys.exit(delete_program(masterconf_path, program_name))
