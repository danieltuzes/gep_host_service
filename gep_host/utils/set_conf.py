import os
from configparser import ConfigParser, ExtendedInterpolation
from pathlib import Path


def set_conf(config: dict):
    pgk_root = Path(os.path.dirname(__file__)).parent.parent
    masterconf_path = os.path.join(pgk_root, "config", "MasterConfig.cfg")

    masterconf = ConfigParser(interpolation=ExtendedInterpolation())
    masterconf.read(masterconf_path)

    prg_conf_path = os.path.join(
        pgk_root, masterconf.get("inputs", "settings"))
    prg_config = ConfigParser(interpolation=ExtendedInterpolation())
    prg_config.read(prg_conf_path)

    root_rel = prg_config.get("settings", "root", fallback="..")
    root_rel = prg_config.get("settings", "root", fallback="..")
    root = os.path.normpath(os.path.join(pgk_root, root_rel))
    config["ROOT"] = root

    config['SECRET_KEY'] = 'your_secret_key'

    config["PRGR"] = os.path.join(root, 'programs')
    config["RUNR"] = os.path.join(root, 'runs')
    config["LIBR"] = os.path.join(root, 'libs')

    for folder in ["PRGR", "RUNR", "LIBR"]:
        if not os.path.isdir(config[folder]):
            os.makedirs(config[folder])

    config["PRG"] = os.path.join(root, 'programs/program_details.csv')
    config["RUN"] = os.path.join(root, 'runs/run_details.csv')
    config["LIB"] = os.path.join(root, 'libs/lib_details.csv')

    config["port"] = int(prg_config.get("settings", "port",
                                        fallback="5000"))
    config["service_name"] = prg_config.get("settings", "service_name",
                                            fallback="GEP host")
    config["host_to"] = prg_config.get("settings", "host_to",
                                       fallback="0.0.0.0")
    config["salt"] = prg_config.get("settings", "salt",
                                    fallback="my_secret_key")
    config["email_patter"] = prg_config.get("settings", "email_pattern",
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
