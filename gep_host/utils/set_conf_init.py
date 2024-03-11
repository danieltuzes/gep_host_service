import os
from configparser import ConfigParser, ExtendedInterpolation
from pathlib import Path

from typing import List
import os
from configparser import ConfigParser, ExtendedInterpolation
from pathlib import Path
from typing import List
import pandas as pd


def create_csv_if_not_exists(colnames: List[str], fname: str) -> None:
    if not os.path.isfile(fname):
        df = pd.DataFrame(columns=colnames)
        df.to_csv(fname, index=False)


def set_folders(pgk_root, prg_config, config):
    root_rel = prg_config.get("settings", "root", fallback="..")
    root = os.path.normpath(os.path.join(pgk_root, root_rel))
    config["ROOT"] = root

    config['SECRET_KEY'] = 'your_secret_key'

    config["PRGR"] = os.path.join(root, 'programs')
    config["RUNR"] = os.path.join(root, 'runs')
    config["LIBR"] = os.path.join(root, 'libs')
    config['FLSR'] = os.path.join(root, 'files')

    for folder in ["PRGR", "RUNR", "LIBR", "FLSR"]:
        if not os.path.isdir(config[folder]):
            os.makedirs(config[folder])


def set_csv_files(root, config):
    config["PRG"] = os.path.join(root, 'programs/program_details.csv')
    config["RUN"] = os.path.join(root, 'runs/run_details.csv')
    config["LIB"] = os.path.join(root, 'libs/lib_details.csv')
    config["FLE"] = os.path.join(root, 'file_data.csv')
    create_csv_if_not_exists(["program_name", "upload_date", "python_version",
                              "status", "PID", "zip_fname", "selected_libs",
                              "def_args", "source", "inputs", "outputs",
                              "version"], config["PRG"])
    create_csv_if_not_exists(["program_name", "purpose", "python_args",
                              "setup_date", "status", "uploaded_files",
                              "inherited_files", "registered_files",
                              "undefineds", "outputs", "comment",
                              "notifications", "PID"], config["RUN"])
    create_csv_if_not_exists(["lib_name", "upload_date", "python_version",
                              "status", "PID", "zip_fname", "selected_libs",
                              "def_args", "source", "inputs", "outputs",
                              "version"], config["LIB"])
    create_csv_if_not_exists(["filename", "upload_date", "size",
                              "hash", "comment", "used_in"], config["FLE"])


def set_other_settings(prg_config, config):
    config["port"] = int(prg_config.get("settings", "port",
                                        fallback="5000"))
    config["service_name"] = prg_config.get("settings", "service_name",
                                            fallback="GEP host")
    config["host_to"] = prg_config.get("settings", "host_to",
                                       fallback="0.0.0.0")
    config["salt"] = prg_config.get("settings", "salt",
                                    fallback="my_secret_key")
    config["email_pattern"] = prg_config.get("settings", "email_pattern",
                                             fallback="[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

    config["email_placeholder"] = prg_config.get("settings", "email_placeholder",
                                                 fallback="developer_ID@company.com, manager@company.com")
    config["host_name"] = prg_config.get("settings", "host_name",
                                         fallback="localhost")
    activate = prg_config.get("settings", "activate",
                              fallback="conda activate ")
    if activate.startswith('"') and activate.endswith('"'):
        activate = activate[1:-1]
    config["activate"] = activate
    config["lib_def_path"] = prg_config.get("settings", "lib_def_path",
                                            fallback="bin64")
    config["git_example"] = prg_config.get("settings", "git_example",
                                           fallback="https://github.com/username/repository.git")
    config["git_branch"] = prg_config.get("settings", "git_branch",
                                          fallback="master ")
    config["stripe_color"] = prg_config.get("settings", "stripe_color",
                                            fallback="#eceef0")


def set_conf(config: dict) -> str:
    pgk_root = Path(os.path.dirname(__file__)).parent.parent
    masterconf_path = os.path.join(pgk_root, "config", "MasterConfig.cfg")

    masterconf = ConfigParser(interpolation=ExtendedInterpolation())
    masterconf.read(masterconf_path)

    # setting folders
    prg_conf_path = os.path.join(
        pgk_root, masterconf.get("inputs", "settings"))
    prg_config = ConfigParser(interpolation=ExtendedInterpolation())
    prg_config.read(prg_conf_path)

    set_folders(pgk_root, prg_config, config)
    root = config["ROOT"]
    set_csv_files(root, config)
    set_other_settings(prg_config, config)
    return prg_conf_path


def load_pages(config: dict, prg_conf_path: str) -> None:
    prg_config = ConfigParser(interpolation=ExtendedInterpolation())
    prg_config.read(prg_conf_path)
    config["static pages"] = {}
    pages_section = prg_config["static pages"]
    for key in pages_section:
        config["static pages"][key] = pages_section.get(key)
