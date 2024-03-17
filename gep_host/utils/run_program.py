"""Run the program from webservice or from cmd line."""
import argparse
import datetime
import os
import subprocess
import sys
from configparser import ConfigParser, ExtendedInterpolation
import json
import traceback
import shutil
from typing import Union, Dict, List, Tuple
import io
import re
import smtplib
import socket
import psutil
import time

import pandas as pd
from werkzeug.utils import secure_filename
from flask import Request, current_app, flash
from unidecode import unidecode


def id_row(details: pd.DataFrame, prg_name: str, purp: str):
    """Shorten to select a row."""
    return ((details['program_name'] == prg_name) &
            (details['purpose'] == purp))


def extract_emails(emails_input: str) -> List[str]:
    email_pattern = current_app.config["email_pattern"]
    return re.findall(email_pattern, emails_input)


def send_email(subject: str, body: str, receiver_emails: List[str]) -> None:
    """Send an email with the message body to the recipients."""
    hostname = socket.gethostname()
    sender_email = f"gep_host_service@{hostname}"

    # Construct the email content
    message = unidecode(f"Subject: {subject}\n\n{body}")

    ret = 0
    for receiver_email in receiver_emails:
        try:
            # Use a context manager to ensure the session is properly closed
            with smtplib.SMTP("localhost") as server:
                server.sendmail(sender_email, receiver_email, message)
        except smtplib.SMTPException as e:
            ret = e
        finally:
            return ret


def input_and_config(request: Request,
                     prg_name: str,
                     purp: str,
                     setup_folder: str) -> Tuple[Dict,
                                                 Dict,
                                                 Dict,
                                                 List[str],
                                                 Dict]:
    """Save the inputs and update the config file."""
    from .helpers import extract_file
    conf = current_app.config

    # save all the inputs
    input_folder = os.path.join(setup_folder, "inputs")
    os.makedirs(input_folder, exist_ok=True)
    masterinput = request.files["masterinput"]
    prgs = pd.read_csv(conf["PRG"], dtype=str)
    inputs = Dict[str, str]
    inputs = json.loads(prgs.loc[prgs.program_name == prg_name,
                                 "inputs"].iloc[0])
    inherits = {}
    uploads = {}
    reg_files = {}
    undefineds = []
    outputs = {}

    # if input is provided as a zip or tar.gz via masterinput
    if masterinput.filename != "":
        masterinput_base_path = os.path.join(setup_folder, "masterinput")
        os.makedirs(masterinput_base_path, exist_ok=True)
        file_data = io.BytesIO(masterinput.read())
        if not extract_file(file_data, masterinput_base_path):
            # shutil.rmtree(setup_folder)  # turned off for debugging
            return "Uploaded masterinput is not a zip or tar.gz file."
        masteri_full_path = os.path.join(
            masterinput_base_path, "MasterInput.cfg")
        if not os.path.isfile(masteri_full_path):
            # shutil.rmtree(setup_folder)  # turned off for debugging
            return "Uploaded masterinput has no MasterInput.cfg in the root."
        master_conf = ConfigParser(interpolation=ExtendedInterpolation())
        with open(masteri_full_path, 'r', encoding="utf-8") as ifile:
            master_conf.read_file(ifile)
        if not master_conf.has_section("inputs"):
            # shutil.rmtree(setup_folder)  # turned off for debugging
            return "No inputs section in MasterInput.cfg"
        for master_input in master_conf.options("inputs"):
            relpath = master_conf.get("inputs", master_input)
            path = os.path.join("masterinput", relpath)
            uploads[master_input] = path
        for input_name in inputs:
            if input_name not in uploads:
                if inputs[input_name] is not None:
                    inherits[input_name] = inputs[input_name]
                else:
                    undefineds.append(input_name)

    else:  # if input is provided as individual files
        for input_name, path in inputs.items():
            # if inheritable and checked, inherit, and don't save
            selected_option = request.form.get(f'{input_name}_option')
            if path is not None and selected_option == "inherit":
                inherits[input_name] = path
                continue

            # save the file only if provided
            elif selected_option == "upload":
                file = request.files[input_name]
                fname = secure_filename(file.filename)
                if fname == "":
                    flash(f"No file is selected for {input_name}. This input is skipped.",
                          "warning")
                    undefineds.append(input_name)
                    continue
                file.save(os.path.join(input_folder, fname))
                path = os.path.join("inputs", fname)
                uploads[input_name] = path
                continue

            elif selected_option == "register":
                reg_file = request.form.get(f'{input_name}_text')
                if reg_file is None or reg_file != "":
                    flash(f"Registered file {reg_file} for {input_name} is not valid.",
                          "warning")
                    undefineds.append(input_name)
                    continue
                files_path = os.path.join(conf["ROOT"],
                                          "file_data.csv")
                files = pd.read_csv(files_path)
                matches = files.loc[files["filename"] == reg_file]
                if matches.empty:
                    flash(f"Registered file {reg_file} for {input_name} is not found.",
                          "warning")
                    undefineds.append(input_name)
                    continue
                if pd.isna(matches["hash"].iloc[0]):
                    directory = matches["dir"].iloc[0]
                else:
                    directory = current_app.config["FLSR"]
                path = os.path.join(directory, reg_file)
                reg_files[input_name] = path
                used_in: List[str] = json.loads(matches["used_in"].iloc[0])
                used_in.append(prg_name + "__" + purp)
                files.loc[files["filename"] == reg_file,
                          "used_in"] = json.dumps(used_in)
                continue

            undefineds.append(input_name)

        if "files" in locals():
            files.to_csv(files_path, index=False)

    # update the config
    # update the input fields
    config_file = os.path.join(setup_folder, 'config', 'MasterConfig.cfg')
    config = ConfigParser(interpolation=ExtendedInterpolation())
    if os.path.isfile(config_file):
        config.read(config_file)
        if 'Root' in config and 'RootDir' in config['Root']:
            config.set('Root', 'RootDir', setup_folder)
            config["DEFAULT"] = {}
        for upload, path in uploads.items():
            uploaded_path = os.path.join(setup_folder, path)
            config.set('inputs', upload, uploaded_path)
        for regf, path in reg_files.items():
            config.set('inputs', regf, path)
        for undefined in undefineds:
            config.set('inputs', undefined, "")

        # get output paths
        if config.has_section("outputs"):
            for ofile in config.options("outputs"):
                ofilepath = os.path.relpath(config.get("outputs", ofile),
                                            setup_folder)
                outputs[ofile] = ofilepath
        with open(config_file, 'w') as configfile:
            config.write(configfile)

    return inherits, uploads, reg_files, undefineds, outputs


def init_run(request: Union[Request, Dict[str, str]]) -> Union[int, str]:
    """Process the run request, and create detached run."""
    from .helpers import alnum, safer_call, concat_to, filename_to_html_id
    from .replacer import LowerPriorityPopen
    try:
        from flask import current_app
        conf = current_app.config
    except Exception:
        from gep_host.utils.set_conf_init import set_conf
        conf = {}
        set_conf(conf, request["masterconf_path"])

    # check if the purpose is unique
    if isinstance(request, Request):
        prg_name = request.form["program_name"]
        purp = alnum(request.form["purpose"], "_-.")
    else:
        prg_name = request["program_name"]
        purp = request["purpose"]
        python_args = request["python_args"]

    setup_folder = os.path.join(conf["ROOT"], "runs", prg_name, purp)
    if os.path.isdir(setup_folder):
        return ("Run setup is unsuccessful. "
                "Cannot save the run files to a new folder. "
                "Is the purpose name unique?")

    # copy the program to a new location
    masterfolder = os.path.join(conf["ROOT"], "programs", prg_name)
    shutil.copytree(masterfolder, setup_folder)

    if isinstance(request, Request):
        inherits, uploads, reg_files, undefineds, outputs = \
            input_and_config(request, prg_name, purp, setup_folder)
        python_args = safer_call(request.form["args"])
        notifications = extract_emails(request.form["notifications"])
        comment = request.form["comment"]
    else:
        uploads = {}
        inherits = {}
        reg_files = {}
        undefineds = []
        outputs = {}
        comment = "automated test run"
        notifications = []

    new_entry = pd.DataFrame({
        'program_name': [prg_name],
        'purpose': [purp],
        'python_args': [python_args],
        'setup_date': [datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        'status': ['set up'],
        'uploaded_files': [json.dumps(uploads)],
        'inherited_files': [json.dumps(inherits)],
        'registered_files': [json.dumps(reg_files)],
        'undefineds': [json.dumps(undefineds)],
        'outputs': [json.dumps(outputs)],
        'comment': [comment],
        'notifications': [json.dumps(notifications)]
    })
    concat_to(new_entry, conf["RUN"])

    # start the execution in a detached process
    setup_folder = os.path.join(conf["ROOT"], 'runs', prg_name, purp)
    cmd = (f"python {__file__} {conf['masterconf_path']} "
           f"{prg_name} {purp}")
    with open(os.path.join(setup_folder, "run_output_and_error.log"), 'w') as logf:
        proc = LowerPriorityPopen(cmd, shell=True,
                                  cwd=os.path.dirname(__file__),
                                  stdout=logf, stderr=logf)

    # set run information
    runs = pd.read_csv(conf["RUN"], dtype=str)
    runs.loc[(runs['program_name'] == prg_name) &
             (runs['purpose'] == purp), 'PID'] = proc.pid
    runs.to_csv(conf["RUN"], index=False)
    run_id = f"{filename_to_html_id(prg_name)}__{purp}"
    body = (f"A run of program {prg_name} with purpose {purp} "
            "is successfully triggered. Emails regardless of the outcome "
            "will be sent. Visit "
            f"http://{conf['host_name']}:{conf['port']}/runs#{run_id}"
            " for the run page for further details.")
    send_email("gep_host run trigger", body, notifications)
    return 0


def wait_in_queue(prg_name: str, purp: str, conf: dict, body: str) -> bool:
    while True:
        runs = pd.read_csv(conf["RUN"], dtype=str).fillna("")
        row_condition = id_row(runs, prg_name, purp)
        row_id = runs[row_condition].index

        row_id = row_id[0]
        current_status = runs.at[row_id, 'status']
        cpu_usage = psutil.cpu_percent(interval=0.5)

        if cpu_usage > 50:
            body += (f"Waiting for CPU, time: {datetime.datetime.now()}.\n")
            if not current_status.startswith('queue'):
                # Assign the next available priority
                queue_count = runs['status'].str.startswith('queue').sum()
                priority = queue_count + 1
                runs.at[row_id, 'status'] = f'queue {priority}'
                runs.to_csv(conf["RUN"], index=False)

            time.sleep(2 ** priority)

        else:
            # Set the current run to 'running'
            runs.at[row_id, 'status'] = 'running'

            # Reorganize the queue to fill any gaps
            queued_runs = runs[runs['status'].str.startswith(
                'queue')].sort_values(by='status')
            for new_priority, idx in enumerate(queued_runs.index, start=1):
                runs.at[idx, 'status'] = f'queue {new_priority}'

            runs.to_csv(conf["RUN"], index=False)
            break


def run_program(masterconf_path: str, prg_name: str, purp: str):
    from gep_host.utils.set_conf_init import set_conf
    conf = {}
    set_conf(conf, masterconf_path)

    code = 0
    body = (f"The program {prg_name} with purpose {purp} "
            f"using master conf at {masterconf_path} ")

    try:
        # Update status in run_details.csv
        wait_in_queue(prg_name, purp, conf, body)

        # Activate the conda environment and run the program
        activate_env_command = f'{conf["activate"]}{prg_name}'
        runs = pd.read_csv(conf["RUN"], dtype=str).fillna("")
        args = runs.loc[id_row(runs, prg_name, purp), 'python_args'].iloc[0]
        i_cmd = f'{activate_env_command} && python {args}'
        setup_folder = os.path.join(conf["RUNR"], prg_name, purp)
        proc = subprocess.run(i_cmd, shell=True, cwd=setup_folder, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              check=True)

        print(proc.stdout, flush=True)

        # compress the whole folder to offer for download
        zip_file = os.path.join(conf["ROOT"],
                                f"{program_name}__{purp}.zip")
        shutil.make_archive(zip_file[:-4], 'zip',
                            root_dir=setup_folder, base_dir='.')
        shutil.move(zip_file, setup_folder)

        # Update status in run_details.csv to completed
        runs.loc[id_row(runs, prg_name, purp), 'status'] = 'Completed'
        runs.loc[id_row(runs, prg_name, purp) == prg_name,
                 'PID'] = ''
        body += "is successfully completed."

    except subprocess.CalledProcessError as err:
        code = 1
        print(f"Error calling subprocess: {err}")
        print(traceback.format_exc())
        print("Standard error:", err.stdout, sep="\n")
        runs.loc[id_row(runs, prg_name, purp), 'status'] = \
            f'Completed with error 1'
        body += "had an error upon calling the program."
    except Exception as err:
        code = 2
        print(f"Error in python script: {err}")
        print(traceback.format_exc())
        runs.loc[id_row(runs, prg_name, purp), 'status'] = \
            f'Completed with error 2'
        body += "had an error upon trying to call the program."
    finally:
        runs.to_csv(conf["RUN"], index=False)
        body += (" See more details on "
                 f"http://{conf['host_name']}:{conf['port']}/runs#{prg_name}__{purp} ")
        notifs = runs.loc[id_row(runs, prg_name, purp),
                          'notifications'].iloc[0]
        receiver_emails = json.loads(notifs)
        send_email("gep_host run trigger", body, receiver_emails)
        if code != 0:
            sys.exit(code)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Run a specific program with configurations.')
    parser.add_argument('master_config',
                        metavar='path/to/MasterConfig.cfg',
                        help=('Required: path to the master config file. '
                              'This file contains the paths for the service.'))
    parser.add_argument('program_name',
                        help='Name unique of the program.')
    parser.add_argument('purpose',
                        help='The unique purpose within the program name.')

    args = parser.parse_args()
    masterconf_path = args.master_config
    program_name = args.program_name
    purpose = args.purpose
    run_program(masterconf_path, program_name, purpose)
    sys.exit(0)
