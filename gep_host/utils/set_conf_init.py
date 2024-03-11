import argparse
from configparser import ConfigParser, ExtendedInterpolation
import logging
import os
from pathlib import Path
from typing import List

import pandas as pd


def create_csv_if_not_exists(colnames: List[str], fname: str) -> None:
    if not os.path.isfile(fname):
        df = pd.DataFrame(columns=colnames)
        df.to_csv(fname, index=False)


def set_folders(host_root, config):
    config["ROOT"] = host_root

    config["PRGR"] = os.path.join(host_root, 'programs')
    config["RUNR"] = os.path.join(host_root, 'runs')
    config["LIBR"] = os.path.join(host_root, 'libs')
    config["FLSR"] = os.path.join(host_root, 'files')

    for folder in ["PRGR", "RUNR", "LIBR", "FLSR"]:
        if not os.path.isdir(config[folder]):
            os.makedirs(config[folder])


def set_csv_files(host_root, config):
    config["PRG"] = os.path.join(host_root, 'programs/program_details.csv')
    config["RUN"] = os.path.join(host_root, 'runs/run_details.csv')
    config["LIB"] = os.path.join(host_root, 'libs/lib_details.csv')
    config["FLE"] = os.path.join(host_root, 'file_data.csv')
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
                              "hash", "comment", "used_in", "dir"], config["FLE"])


def set_other_settings(host_settings, config):
    config["port"] = int(host_settings.get("settings", "port",
                                           fallback="5000"))
    config["service_name"] = host_settings.get("settings", "service_name",
                                               fallback="GEP host")
    config["host_to"] = host_settings.get("settings", "host_to",
                                          fallback="0.0.0.0")
    config["salt"] = host_settings.get("settings", "salt",
                                       fallback="my_secret_key")
    config["email_pattern"] = host_settings.get("settings", "email_pattern",
                                                fallback="[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

    config["email_placeholder"] = host_settings.get("settings", "email_placeholder",
                                                    fallback="developer_ID@company.com, manager@company.com")
    config["host_name"] = host_settings.get("settings", "host_name",
                                            fallback="localhost")
    activate = host_settings.get("settings", "activate",
                                 fallback="conda activate ")
    if activate.startswith('"') and activate.endswith('"'):
        activate = activate[1:-1]
    config["activate"] = activate
    config["lib_def_path"] = host_settings.get("settings", "lib_def_path",
                                               fallback="bin64")
    config["git_example"] = host_settings.get("settings", "git_example",
                                              fallback="https://github.com/username/repository.git")
    config["git_branch"] = host_settings.get("settings", "git_branch",
                                             fallback="master ")
    config["stripe_color"] = host_settings.get("settings", "stripe_color",
                                               fallback="#eceef0")


def set_conf(config: dict, args: argparse.Namespace) -> str:
    """Set the configuration for the host service.

    Parameters
    ----------
    config : dict
        This is populated with the configuration settings.
    args : argparse.Namespace
        The command line arguments that tells the master config file path.

    Returns
    -------
    str
        Path to the host settings file.

    Raises
    ------
    FileNotFoundError
        If the master config file or the host settings file is not found.
    """
    config['SECRET_KEY'] = 'your_secret_key'

    # set up folders and csv files
    masterconf_path = os.path.abspath(args.master_config)
    if not os.path.isfile(masterconf_path):
        logging.error("MasterConfig.cfg not found at %s", masterconf_path)
        raise FileNotFoundError(
            f"MasterConfig.cfg not found at {masterconf_path}")

    masterconf = ConfigParser(interpolation=ExtendedInterpolation())
    masterconf.read(masterconf_path)
    host_root = os.path.abspath(masterconf.get("Outputs", "HostRoot"))

    set_folders(host_root, config)
    set_csv_files(host_root, config)

    # set other settings
    host_settings_path = masterconf.get("Inputs", "Settings")
    if not os.path.isfile(host_settings_path):
        logging.error("Host settings not found at %s", host_settings_path)
        raise FileNotFoundError(
            f"Host settings not found at {host_settings_path}")
    host_settings = ConfigParser(interpolation=ExtendedInterpolation())
    host_settings.read(host_settings_path)

    set_other_settings(host_settings, config)

    return host_settings_path


def load_pages(config: dict, prg_conf_path: str) -> None:
    prg_config = ConfigParser(interpolation=ExtendedInterpolation())
    prg_config.read(prg_conf_path)
    config["static pages"] = {}
    pages_section = prg_config["static pages"] if "static pages" in prg_config else {
    }
    for key in pages_section:
        config["static pages"][key] = pages_section.get(key)
