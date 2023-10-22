import os
import subprocess
import shutil
import sys
import traceback
import json
import pandas as pd


def run_and_verify(cmd: str, cwd=None):
    proc = subprocess.run(cmd, cwd=cwd, shell=True, text=True,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(returncode=proc.returncode,
                                            cmd=cmd, stderr=proc.stdout)


def init_del(program_name: str):
    cmd = f"python {__file__} {program_name}"
    proc = subprocess.run(cmd, shell=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout


def remove_val_from_json(json_str, val_2_remove):
    mylist = json.loads(json_str)
    new_list = [val for val in mylist if val != val_2_remove]
    return json.dumps(new_list)


def delete_program(program_name):
    """Delete a program.

    Parameters
    ----------
    program_name : _type_
        Delete this program and its zip file.

    """
    # the price of using the same file where the deletion is initiated from python
    # and where the console script's deletion is implemented
    from set_conf import set_conf
    from helpers import remove_readonly
    config = {}
    set_conf(config)

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

        if os.path.isfile(config["LIB"]):
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
    # The script expects 3 command-line arguments: program_name, path_to_zip, python_version
    if len(sys.argv) != 2:
        print("Usage: python delete_program.py <program_name>")
        sys.exit(1)

    program_name = sys.argv[1]

    sys.exit(delete_program(program_name))
