"""Run the program from webservice or from cmd line."""

import datetime
import os
import subprocess
import sys
from pathlib import Path
from configparser import ConfigParser, ExtendedInterpolation
import json
import traceback
import zipfile
import shutil
from typing import Union, Dict, List
import io
import re
import smtplib
import socket

import pandas as pd
from werkzeug.utils import secure_filename
import flask
from unidecode import unidecode

PROJ_ROOT = Path(os.path.dirname(__file__)).parent.parent.parent
RUN_DETAILS_CSV = os.path.join(PROJ_ROOT, 'runs', 'run_details.csv')
PROGRAM_DETAILS_CSV = os.path.join(PROJ_ROOT,
                                   'programs/program_details.csv')


def id_row(details: pd.DataFrame, prg_name: str, purp: str):
    """Shorten to select a row."""
    return ((details['program_name'] == prg_name) &
            (details['purpose'] == purp))


def extract_emails(emails_input: str) -> List[str]:
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
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


def init_run(request: flask.Request) -> Union[int, str]:
    """Process the run request, and create detached run."""
    from .helpers import alnum, safer_call, concat_to

    # check if the purpose is unique
    prg_name = request.form["program_name"]
    purp = alnum(request.form["purpose"], "_-.")
    setup_folder = os.path.join(PROJ_ROOT, "runs", prg_name, purp)
    if os.path.isdir(setup_folder):
        return ("Run setup is unsuccessful. "
                "Cannot save the run files to a new folder."
                "Is the purpose name unique?")

    # copy the program to a new location
    masterfolder = os.path.join(PROJ_ROOT, "programs", prg_name)
    shutil.copytree(masterfolder, setup_folder)

    # save all the inputs
    input_folder = os.path.join(setup_folder, "inputs")
    os.makedirs(input_folder, exist_ok=True)
    masterinput = request.files["masterinput"]
    prgs = pd.read_csv(PROGRAM_DETAILS_CSV, dtype=str)
    inputs = Dict[str, str]
    inputs = json.loads(prgs.loc[prgs.program_name == prg_name,
                                 "inputs"].iloc[0])
    inherits = {}
    uploads = {}
    undefineds = []
    if masterinput.filename != "":
        masterinput_path = os.path.join(setup_folder, "masterinput")
        os.makedirs(masterinput_path, exist_ok=True)
        file_data = io.BytesIO(masterinput.read())
        if zipfile.is_zipfile(file_data):
            with zipfile.ZipFile(file_data) as zf:
                zf.extractall(masterinput_path)
        else:
            # shutil.rmtree(setup_folder)
            return "Uploaded masterinput is not a zip file."
        master_confpath = os.path.join(masterinput_path, "MasterInput.cfg")
        if not os.path.isfile(master_confpath):
            # shutil.rmtree(setup_folder)
            return "Uploaded masterinput has no MasterInput.cfg in the root."
        master_conf = ConfigParser(interpolation=ExtendedInterpolation())
        with open(master_confpath, 'r', encoding="utf-8") as ifile:
            master_conf.read_file(ifile)
        if not master_conf.has_section("inputs"):
            # shutil.rmtree(setup_folder)
            return "No input section in MasterInput.cfg"
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
    else:
        for input_name, path in inputs.items():
            # if inheritable and checked, inherit, and don't save
            if path is not None:
                checkbox_value = request.form.get(f'check{input_name}')
                if checkbox_value:
                    inherits[input_name] = path
                    continue

            # save the file only if provided
            file = request.files[input_name]
            fname = secure_filename(file.filename)
            if fname != "":
                file.save(os.path.join(input_folder, fname))
                path = os.path.join("inputs", fname)
                uploads[input_name] = path
                continue

            undefineds.append(input_name)

    # update the config
    # update the input fields
    config_file = os.path.join(setup_folder, 'config', 'MasterConfig.cfg')
    config = ConfigParser(interpolation=ExtendedInterpolation())
    config.read(config_file)
    if 'Root' in config and 'RootDir' in config['Root']:
        config.set('Root', 'RootDir', setup_folder)
        config["DEFAULT"] = {}
    for upload, path in uploads.items():
        uploaded_path = os.path.join(setup_folder, path)
        config.set('inputs', upload, uploaded_path)
    for undefined in undefineds:
        config.set('inputs', undefined, "")

    # get output paths
    outputs = {}
    for ofile in config.options("outputs"):
        ofilepath = os.path.relpath(config.get("outputs", ofile),
                                    setup_folder)
        outputs[ofile] = ofilepath
    with open(config_file, 'w') as configfile:
        config.write(configfile)

    python_args = safer_call(request.form["args"])
    notifications = extract_emails(request.form["notifications"])
    new_entry = pd.DataFrame({
        'program_name': [prg_name],
        'purpose': [purp],
        'python_args': [python_args],
        'setup_date': [datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        'status': ['set up'],
        'uploaded_files': [json.dumps(uploads)],
        'inherited_files': [json.dumps(inherits)],
        'undefineds': [json.dumps(undefineds)],
        'outputs': [json.dumps(outputs)],
        'comment': request.form["comment"],
        'notifications': [json.dumps(notifications)]
    })
    concat_to(new_entry, RUN_DETAILS_CSV)

    setup_folder = os.path.join(PROJ_ROOT, 'runs', prg_name, purp)
    cmd = f"python {__file__} {prg_name} {purp}"
    with open(os.path.join(setup_folder, "run_output_and_error.log"), 'w') as logf:
        proc = subprocess.Popen(cmd, shell=True,
                                cwd=os.path.dirname(__file__),
                                stdout=logf, stderr=logf)

    runs = pd.read_csv(RUN_DETAILS_CSV, dtype=str)
    runs.loc[(runs['program_name'] == prg_name) &
             (runs['purpose'] == purp), 'PID'] = proc.pid

    body = (f"A run of program {prg_name} with purpose {purp} "
            "is successfully triggered. Emails regardless of the outcome "
            "will be sent. Visit <a href='localhost:5000/runs'>the run page</a> "
            "for further details.")
    send_email("gep_host run trigger", body, notifications)
    return 0


def run_program(prg_name, purp):
    from helpers import zipdir
    code = 0
    body = f"The program {prg_name} with purpose {purp} "
    try:
        # Update status in run_details.csv
        runs = pd.read_csv(RUN_DETAILS_CSV, dtype=str).fillna("")
        runs.loc[id_row(runs, prg_name, purp), 'status'] = 'running'
        runs.to_csv(RUN_DETAILS_CSV, index=False)

        # Activate the conda environment and run the program
        activate_env_command = f'conda activate {prg_name}'
        args = runs.loc[id_row(runs, prg_name, purp), 'python_args'].iloc[0]
        i_cmd = f'{activate_env_command} && python -m {args}'
        setup_folder = os.path.join(PROJ_ROOT, 'runs', prg_name, purp)
        proc = subprocess.run(i_cmd, shell=True, cwd=setup_folder, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              check=True)

        # compress the whole folder to offer for download
        zip_file = os.path.join(setup_folder,
                                f"{program_name}__{purp}.zip")
        zipdir(setup_folder, zip_file)

        # Update status in run_details.csv to completed
        runs.loc[id_row(runs, prg_name, purp), 'status'] = 'Completed'
        runs.loc[id_row(runs, prg_name, purp) == prg_name,
                 'PID'] = ''
        print(proc.stdout)
        body += f"is successfully completed."

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
        runs.to_csv(RUN_DETAILS_CSV, index=False)
        body += (" See more details on "
                 f"<a href='{socket.gethostname()}'>the run page.</a>")
        notifs = runs.loc[id_row(runs, prg_name, purp),
                          'notifications'].iloc[0]
        receiver_emails = json.loads(notifs)
        send_email("gep_host run trigger", body, receiver_emails)
        if code != 0:
            sys.exit(code)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python run_program.py <program_name> <purpose>")
        sys.exit(1)

    program_name = sys.argv[1]
    purpose = sys.argv[2]

    run_program(program_name, purpose)
    sys.exit(0)
