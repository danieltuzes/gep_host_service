import argparse
import os
import subprocess
import json
import sys
from datetime import datetime
from configparser import ConfigParser, ExtendedInterpolation
from typing import Union, List, Dict, Tuple
import traceback
import shutil
import re
import tempfile

import pandas as pd
from flask import current_app
import git


def init_install(program_name,
                 program_zip_path,
                 python_version,
                 selected_libs,
                 def_args,
                 git_source: Dict[str, str]) -> Union[int, str]:

    # trigger the installation
    selected_libs_str = ""
    if selected_libs:
        selected_libs_str = "--list-of-libs " + " ".join(selected_libs)
    masterfolder = os.path.join(current_app.config["PRGR"], program_name)
    os.makedirs(masterfolder)
    if git_source == {}:
        source = program_zip_path
        s_extra = ""
        source = "file upload"
    else:
        source = git_source["git-source-url"]
        s_extra = f' -s {git_source["git-source-ref"]}'
        source_rep = " ".join(git_source.values())

    cmd = (f'python {__file__} {current_app.config["masterconf_path"]} {program_name} {source} '
           f'{python_version} {selected_libs_str} {s_extra}')
    with open(os.path.join(masterfolder,
                           "install_output_and_error.log"), 'w') as logf:
        proc = subprocess.Popen(cmd, shell=True,
                                stdout=logf, stderr=logf)

    # Update program details CSV
    new_entry = pd.DataFrame({
        'program_name': [program_name],
        'upload_date': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        'python_version': [python_version],
        'status': ['installing'],
        'PID': [proc.pid],
        'zip_fname': [program_zip_path],
        'selected_libs': [" ".join(selected_libs)],
        'def_args': [def_args],
        'source': [source_rep],
        'inputs': json.dumps({}),
        'outputs': json.dumps({}),
        'version': json.dumps({})
    })
    df = pd.read_csv(current_app.config["PRG"], dtype=str)
    if len(df[df['program_name'] == program_name]) == 0:
        df = pd.concat([df, new_entry], ignore_index=True)
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


def get_version_from_init(init_path):
    with open(init_path, 'r') as f:
        contents = f.read()
        version_match = re.search(
            r"^__version__\s*=\s*['\"]([^'\"]*)['\"]", contents, re.MULTILINE)
        if version_match:
            return version_match.group(1)
    return None


def get_versions(root) -> str:
    """Get the versions of modules in the specified root directory.

    Parameters:
    -----------
    root (str): The root directory to search for module versions.

    Returns:
    --------
    str: A string containing the versions of the modules found in the root directory.
         If no valid modules with version info are found, returns "No valid modules with version info found in the root."
    """
    versionstrs = []

    def add_ver_from_file(location, versionstr):
        version = get_version_from_init(location)
        if version:
            versionstr += f"version: {version}"
            versionstrs.append(versionstr)

    # Helper function to check for module version in a directory
    def check_dir_ver(rel_root, item):
        # Check if the item is a directory and contains __init__.py

        versionstr = ""
        if item:
            versionstr = f"{item}: "

        init_loc = os.path.join(rel_root, item, '__init__.py')
        main_loc = os.path.join(rel_root, item, '__main__.py')

        version = None

        if os.path.exists(main_loc):
            add_ver_from_file(main_loc, versionstr)
        if os.path.exists(init_loc) and not version:
            add_ver_from_file(init_loc, versionstr)

    # Check the root directory
    check_dir_ver(root, "")

    # Check directories one level deeper
    for item in os.listdir(root):
        item_path = os.path.join(root, item)
        check_dir_ver(root, item)
        if os.path.isdir(item_path):
            for subitem in os.listdir(item_path):
                check_dir_ver(item_path, subitem)

    versions = "; ".join(versionstrs)
    if versions != "":
        return versions
    return "No valid modules with version info found in the root."


def install_program(masterconf_path: str,
                    program_name: str,
                    program_source: Union[str, Tuple[str, str]],
                    required_python_version: str,
                    required_libs: List[str]):
    from gep_host.utils.set_conf_init import set_conf
    from helpers import extract_file, get_orig_fname
    app_conf = {}
    set_conf(app_conf, masterconf_path)

    code = 0
    try:
        # 1. Update status in program_details.csv
        df = pd.read_csv(app_conf["PRG"], dtype=str)
        if len(df[df['program_name'] == program_name]) == 0:
            selected_libs_str = ""
            if required_libs:
                selected_libs_str = "--list-of-libs " + " ".join(required_libs)
            if isinstance(program_source, str):
                program_zip_path = program_source
                source_rep = get_orig_fname(program_source)
            else:
                nowstr = datetime.now().strftime('%Y%m%d%H%M%S')
                program_zip_path = f"{program_name}_{nowstr}.zip"
                source_rep = " ".join(program_source)
            new_entry = pd.DataFrame({
                'program_name': [program_name],
                'upload_date': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
                'python_version': [required_python_version],
                'status': [""],
                'PID': [os.getpid()],
                'zip_fname': [program_zip_path],
                'selected_libs': [selected_libs_str],
                'def_args': [""],
                'source': [source_rep],
                'inputs': json.dumps({}),
                'outputs': json.dumps({}),
                'version': json.dumps({})
            })
            df = pd.concat([df, new_entry], ignore_index=True, axis=0)
        df.loc[df['program_name'] == program_name,
               'status'] = 'getting the files'
        df.to_csv(app_conf["PRG"], index=False)

        # 2. get the files and version info
        masterfolder = os.path.join(app_conf["PRGR"], program_name)
        # Extract zip to the masterfolder
        if isinstance(program_source, str):
            zipf = os.path.join(app_conf["PRGR"], program_source)
            if not extract_file(zipf, masterfolder):
                print(f"Error: failed to extract the file {zipf}")

        # or git clone and checkout
        else:
            tmpdir = tempfile.mkdtemp()
            try:
                repo = git.Repo.clone_from(program_source[0], tmpdir)

                # Initialize and update all submodules
                for submodule in repo.submodules:
                    submodule.update(init=True)

                # Checkout to the desired state
                repo.git.checkout(program_source[1])

                # Copy contents of the temporary directory into masterfolder
                for item in os.listdir(tmpdir):
                    s = os.path.join(tmpdir, item)
                    d = os.path.join(masterfolder, item)
                    if os.path.isdir(s):
                        shutil.copytree(s, d, dirs_exist_ok=True)
                    else:
                        shutil.copy2(s, d)
            finally:
                # Explicitly attempt to delete the temporary directory
                shutil.rmtree(tmpdir, ignore_errors=True)

        version = get_versions(masterfolder)
        df = pd.read_csv(app_conf["PRG"], dtype=str)
        df.loc[df["program_name"] == program_name, "version"] = version

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
        elif os.path.isfile(os.path.join(masterfolder, "requirements.txt")):
            print("requirements.txt is found")
            pip_install_command = ' && pip install -r requirements.txt'
        else:
            pip_install_command = ""
        i_cmd = f'{activate_env_command} {pip_install_command}'
        run_and_verify(i_cmd, cwd=masterfolder)

        # 5. add the libraries
        if len(required_libs) > 0:
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

        # 6. compress the folder if it was git
        if isinstance(program_source, str) is not None:
            df = pd.read_csv(app_conf["PRG"], dtype=str)
            df.loc[df['program_name'] == program_name,
                   'status'] = 'creating the zip from repo'
            df.to_csv(app_conf["PRG"], index=False)
            zip_fname = df.loc[df['program_name'] == program_name,
                               'zip_fname'].iloc[0]
            zip_path = os.path.join(app_conf["PRGR"], zip_fname)
            shutil.make_archive(zip_path[:-4], 'zip',
                                root_dir=masterfolder, base_dir='.')

        # 7. Update status in program_details.csv to installed
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
    parser = argparse.ArgumentParser(
        description="Install a program into GEP Host")

    # Required arguments
    parser.add_argument("master_config",
                        help=('Required: path to the master config file. '
                              'This file contains the paths for the service.'),
                        metavar="path/to/MasterConfig.cfg")
    parser.add_argument("program_name", help="Name of the program")
    parser.add_argument("program_source",
                        help=("Source of the program. "
                              "Zip file location or git repo URL"))
    parser.add_argument("required_python_version",
                        help="Python version for the program")

    # Optional arguments
    parser.add_argument("-s", "--source-specifier",
                        default=None,
                        help=("If program_source is git, "
                              "this defines the commit hash, "
                              "branch or version tag"))
    parser.add_argument("-l", "--list-of-libs", nargs='*',
                        default=[],
                        help="List of libraries for the program")
    args = parser.parse_args()

    master_config = args.master_config
    program_name = args.program_name
    required_python_version = args.required_python_version
    if args.source_specifier is not None:
        program_source = (args.program_source, args.source_specifier)
    else:
        program_source = args.program_source
    list_of_libs = args.list_of_libs

    install_program(master_config,
                    program_name,
                    program_source,
                    required_python_version,
                    list_of_libs)
    print(sys.argv)
    sys.exit(0)
