import json
from datetime import datetime
import os
import shutil
from configparser import ConfigParser, ExtendedInterpolation
import traceback
import zipfile
import platform
import multiprocessing
import logging
from io import StringIO

from flask import render_template, request, redirect, flash, \
    url_for, send_from_directory, send_file, Response, jsonify, Blueprint, current_app
import pandas as pd
from werkzeug.utils import secure_filename
import psutil

from .utils import install_program, delete_program, delete_run, run_program
from .utils.helpers import *


main_routes = Blueprint('main_routes', __name__)


def count_not_status(data: pd.DataFrame, status: str) -> int:
    """Count how many times the col status doesn't start with status."""
    if len(data) == 0:
        return 0
    starts_with = len(data[data.status.str.startswith(status)])
    different = len(data) - starts_with
    return different


def activity(data: pd.DataFrame, type: str) -> str:
    """Generate the message to be displayed."""
    if type == "programs":
        active = count_not_status(data, "Installed")
        active = active
        ret = f"{active} program installation(s) "
    if type == "runs":
        active = count_not_status(data, "Completed")
        ret = f"{active} runs(s) "
    ret += "are in progress."
    return ret


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'zip'


@main_routes.route('/')
def index():
    data = {
        'System': platform.system(),
        'Node': platform.node(),
        'Hostname': current_app.config["host_name"],
        'Release': platform.release(),
        'Version': platform.version(),
        'Machine': platform.machine(),
        'Architecture': platform.architecture()[0],
        'Processor': platform.processor(),
        'Number of Cores': multiprocessing.cpu_count(),
        'Project root': current_app.config["ROOT"]
    }

    # If on Linux, you can get more detailed info with:
    if platform.system() == "Linux":
        # You only get the first element for the version
        data['Libc version'] = platform.libc_ver()[0]
        try:
            # Deprecated since Python 3.5
            data['Distribution'] = platform.linux_distribution()
        except AttributeError:
            data['Distribution'] = "N/A"

    return render_template('index.html', data=data)


@main_routes.route('/programs', methods=['GET', 'POST'])
def programs():
    """Show programs, confirm successful installation."""
    column = request.args.get('column', 'upload_date')
    direction = request.args.get('direction', 'desc')
    if os.path.exists(current_app.config["PRG"]):
        prgs = pd.read_csv(current_app.config["PRG"], dtype=str).fillna("")
        ascending = True if direction == "asc" else False
        prgs.sort_values(by=column, ascending=ascending, inplace=True)
    else:
        prgs = pd.DataFrame()

    libs = pd.DataFrame()
    if os.path.isfile(current_app.config["LIB"]):
        libs = pd.read_csv(current_app.config["LIB"])

    return render_template('programs.html',
                           programs=prgs,
                           libs=libs,
                           column=column,
                           direction=direction,
                           activity=activity(prgs, "programs"))


@main_routes.route('/program_install', methods=['POST'])
def program_install():
    """Receive POST data to install and redirect user."""
    if request.method != 'POST':
        flash("Program install requiested without post data", "warning")
        return programs()

    # Logic for handling the file upload
    file = request.files['program_package']
    if file.filename == "" and "git-source-url" not in request.form:
        flash('No selected zip file or git source', 'warning')
        return redirect(url_for("main_routes.programs"))

    if file.filename != "":
        if not allowed_file(file.filename):
            flash('Not allowed filetype', 'warning')
            return redirect(request.url)

    if "git-source-url" in request.form and "git-source-ref" not in request.form:
        flash('No branch, commit hash or tag specified for git source', 'warning')
        return redirect(request.url)

    # Program details
    program_name = alnum(request.form['unique_program_name'], "_-.")
    python_version_raw = request.form['required_python_version']
    python_version = "".join(
        char for char in python_version_raw if char.isdigit or char == ".")
    selected_libs = request.form.getlist('selected_libs')
    def_args = safer_call(request.form["def_args"])

    # Check uniqueness of program name
    masterfolder = os.path.join(current_app.config["PRGR"], program_name)
    if os.path.isdir(masterfolder):
        flash('Program upload is unsuccessful due to its non-unique name.', 'warning')
        redirect(url_for("main_routes.programs"))

    # save the file or pass git source
    git = {}
    program_zip_path = ""
    if file.filename != "":
        filename = secure_filename(file.filename)
        base, ext = os.path.splitext(filename)
        nowstr = datetime.now().strftime('%Y%m%d%H%M%S')
        t_filename = f"{base}_{nowstr}{ext}"
        program_zip_path = os.path.join(
            current_app.config['PRGR'], t_filename)
        file.save(program_zip_path)
    else:
        git["git-source-url"] = request.form["git-source-url"]
        git["git-source-ref"] = request.form["git-source-ref"]

    # Execute install script in subprocess
    res = install_program.init_install(program_name,
                                       program_zip_path,
                                       python_version,
                                       selected_libs,
                                       def_args,
                                       git)
    if res != 0:
        flash(res, "warning")
    else:
        flash('Program install started', 'success')

    return redirect(url_for("main_routes.programs"))


@main_routes.route('/install_log/<program_name>')
def install_log(program_name: str):
    log_path = os.path.join(current_app.config["PRGR"],
                            program_name, "install_output_and_error.log")
    if os.path.isfile(log_path):
        return send_file(log_path)
    else:
        flash(("The log file has been already removed. "
              "Service integritiy is compromised. Notify the admin."), "warning")
        return programs()


@main_routes.route('/del_program/<program_name>')
def del_program(program_name: str):
    exitcode, stdout = delete_program.init_del(program_name)
    if exitcode != 0:
        flash(f"Couldn't fully delete {program_name}. Details:<br><pre>{stdout}</pre>",
              "warning")
    else:
        flash(f"Successfully deleted program: {program_name}", "success")
    return redirect(url_for("main_routes.programs"))


@main_routes.route('/program/<program_name>')
def get_prg(program_name: str):
    prgs = pd.read_csv(current_app.config["PRG"])
    zip_fname = prgs.loc[prgs["program_name"]
                         == program_name, "zip_fname"].iloc[0]
    f_path = os.path.join(current_app.config["PRGR"], zip_fname)
    orig_fname = zip_fname[:-19] + zip_fname[-4:]

    return send_file(f_path,
                     mimetype='main_routeslication/zip',
                     as_attachment=True,
                     download_name=orig_fname)


@main_routes.route('/runs', methods=['GET'])
def runs():
    column = request.args.get('column', 'setup_date')
    direction = request.args.get('direction', 'desc')
    program_name = request.args.get('program_name')

    # Read the content of run_details.csv, filter and order it
    runs = pd.DataFrame()
    if os.path.exists(current_app.config["RUN"]):
        runs = pd.read_csv(current_app.config["RUN"], dtype=str).fillna("")

        # order
        ascending = True if direction == "asc" else False
        runs.sort_values(by=column, ascending=ascending, inplace=True)

        # filter
        if program_name is not None:
            runs = runs[runs["program_name"] == program_name]

    prgs = pd.DataFrame()
    if os.path.exists(current_app.config["PRG"]):
        prgs = pd.read_csv(current_app.config["PRG"], dtype=str).fillna("")

    prg_to_run = None
    if program_name is not None:
        prg_to_run = prgs.loc[prgs.program_name == program_name].iloc[0]

    return render_template('runs.html',
                           runs=runs,
                           program_name=program_name,
                           prg_to_run=prg_to_run,
                           direction=direction,
                           column=column,
                           activity=activity(runs, "runs"))


@main_routes.route('/trigger_run', methods=['POST'])
def trigger_run():

    if request.method != 'POST':
        flash("Run requested without POST data.", "warning")
        return redirect(url_for("main_routes.runs"))

    ret = run_program.init_run(request)
    if ret != 0:
        flash(ret, "warning")
    else:
        flash("Program set up and run initiated successfully.", "success")

    return redirect(url_for("main_routes.runs"))


@main_routes.route('/users_tokens')
def users_tokens():
    return render_template('users_tokens.html')


@main_routes.route('/program/<program_name>/<path:input_path>')
def get_program_input(program_name, input_path):
    f_path = os.path.join(
        current_app.config["PRGR"], program_name, input_path)
    logging.info("sending %s", f_path)
    return send_from_directory(os.path.dirname(f_path),
                               os.path.basename(f_path))


@main_routes.route('/run/<program_name>/<purpose>/<path:file>')
def get_run_file(program_name, purpose, file):
    f_path = os.path.join(current_app.config["RUNR"],
                          program_name,
                          purpose,
                          file)
    return send_from_directory(os.path.dirname(f_path), os.path.basename(f_path))


@main_routes.route('/del_run/<program_name>/<purpose>')
def del_run(program_name: str, purpose: str):
    exitcode, stdout = delete_run.init_del(program_name, purpose)
    if exitcode != 0:
        msg = "<pre>" + stdout + "</pre>"
        flash(f"Couldn't fully delete {program_name} with purpose {purpose}. Details:<br>{msg}",
              "warning")
    else:
        flash(
            f"Successfully deleted program {program_name} with purpose {purpose}", "success")
    return redirect(url_for("main_routes.runs"))


@main_routes.route('/stop_run/<program_name>/<purpose>')
def stop_run(program_name: str, purpose: str):
    runs = pd.read_csv(current_app.config["RUN"], dtype=str).fillna("")
    pidstr = runs.loc[(runs['program_name'] == program_name) &
                      (runs['purpose'] == purpose), 'PID'].iloc[0]

    if pidstr == "":
        flash("Program has been already completed according to this webservice.", "warning")
        return redirect(url_for("main_routes.runs"))

    pid = int(float(pidstr))

    filter_criteria = (runs['program_name'] == program_name) \
        & (runs['purpose'] == purpose)

    try:
        process = psutil.Process(pid)
        process_exists = True
    except psutil.NoSuchProcess:
        flash(f"No process with PID {pid} found in this OS. Status of the program is updated.",
              "warning")
        runs.loc[filter_criteria, 'status'] = "Completed (terminated)"
        runs.to_csv(current_app.config["RUN"])
    except Exception as e:
        flash(f"An error occurred:<br><pre>{e}</pre>", "warning")

    if process_exists:
        try:
            children = process.children(recursive=True)
            for child in children:
                child.terminate()
        except Exception as e:
            flash(f"Couldn't terminate children process.", "warning")

        try:
            process = psutil.Process(pid)
            process.terminate()
            process.wait(3)

            runs.loc[filter_criteria, 'status'] = "Completed (terminated)"
            runs.to_csv(current_app.config["RUN"])
            flash(f"Process with PID {pid} is terminated.", "success")

        except psutil.NoSuchProcess:
            flash(f"Process PID {pid} existed, but died after its children are closed.",
                  "success")
            runs.loc[filter_criteria, 'status'] = "Completed (terminated)"
            runs.to_csv(current_app.config["RUN"])
        except psutil.TimeoutExpired:
            flash(
                f"Process with PID {pid} did not terminate in time.", "warning")

    conf = current_app.config
    setup_folder = os.path.join(conf["RUNR"],
                                program_name,
                                purpose)
    zip_file = os.path.join(conf["ROOT"],
                            f"{program_name}__{purpose}.zip")
    shutil.make_archive(zip_file[:-4], 'zip',
                        root_dir=setup_folder, base_dir='.')
    shutil.move(zip_file, setup_folder)

    return redirect(url_for("main_routes.runs"))


@main_routes.route('/run_log/<program_name>/<purpose>')
def run_log(program_name: str, purpose: str):
    log_path = os.path.join(current_app.config["RUNR"], program_name, purpose)
    return send_from_directory(log_path, "run_output_and_error.log")


@main_routes.route('/template/<program_name>/')
def get_template(program_name: str):
    conf_path = os.path.join(current_app.config["PRGR"],
                             program_name,
                             "config",
                             "MasterConfig.cfg")
    prg_config = ConfigParser(
        interpolation=ExtendedInterpolation())
    if os.path.isfile(conf_path):
        prg_config.read(conf_path)
        prg_config["DEFAULT"] = {}

    new_conf = ConfigParser()
    if 'inputs' in prg_config:
        new_conf.add_section('inputs')
        for option, path in prg_config.items('inputs'):
            fname = os.path.basename(path)
            new_conf.set('inputs', option, fname)

    string_buffer = StringIO()
    new_conf.write(string_buffer)
    config_string = string_buffer.getvalue()

    response = Response(config_string, content_type="text/plain")
    response.headers["Content-Disposition"] = "attachment; filename=MasterInput.cfg"

    return response


@main_routes.route('/libraries', methods=['GET', 'POST'])
def libraries():
    if request.method == 'POST':
        # Logic for handling the file upload
        file = request.files['library_package']
        if file.filename == '':
            flash('No selected file', 'warning')
            return redirect(request.url)
        if not allowed_file(file.filename):
            flash('Not allowed filetype', 'warning')
            return redirect(request.url)

        # Program details
        library_name = alnum(request.form['unique_library_name'], "_-.")
        path_to_exec = alnum(request.form['path_to_exec'], "_-. (-)/,+~!#")

        # Check uniqueness of library name
        masterfolder = os.path.join(current_app.config["LIBR"], library_name)
        if os.path.isdir(masterfolder):
            flash('Library upload is unsuccessful due to its non-unique name.', 'warning')
            return redirect(request.url)

        # save the file
        filename = secure_filename(file.filename)
        base, ext = os.path.splitext(filename)
        nowstr = datetime.now().strftime('%Y%m%d%H%M%S')
        t_filename = f"{base}_{nowstr}{ext}"
        program_zip_path = os.path.join(current_app.config["LIBR"], t_filename)
        file.save(program_zip_path)

        # extract the file
        try:
            os.makedirs(masterfolder)
            with zipfile.ZipFile(program_zip_path, 'r') as zip_ref:
                zip_ref.extractall(masterfolder)
        except Exception as err:
            msg = f"Error in unzipping the library: {err}"
            msg += f"Details:<br><pre>{traceback.format_exc()}</pre>"
            flash(msg, "warning")
            return redirect(url_for("main_routes.libraries"))

        nowstr = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        file_size = os.stat(program_zip_path).st_size
        file_size_str = f"{file_size:.0f} B"
        if file_size > 2000:
            file_size_str = f"{file_size/1024:.0f} KB"
        if file_size > 2000000:
            file_size_str = f"{file_size/1024/1024:.0f} MB"

        new_entry = pd.DataFrame({
            'library_name': [library_name],
            'path_to_exec': [path_to_exec],
            'upload_date': [nowstr],
            'zip_path': [os.path.relpath(program_zip_path, current_app.config["ROOT"])],
            'orig_filename': [filename],
            'status': ["Installed"],
            'size': [file_size_str],
            'comment': request.form["comment"],
            'used_in': [json.dumps([])]
        })

        libs = pd.DataFrame()
        if os.path.isfile(current_app.config["LIB"]):
            libs = pd.read_csv(current_app.config["LIB"])
        libs = pd.concat([libs, new_entry], ignore_index=True)
        libs.to_csv(current_app.config["LIB"], index=False)
        flash(f"Library {library_name} is successfully uploaded.", "success")
        return redirect(url_for("main_routes.libraries"))

    column = request.args.get('column', 'upload_date')
    direction = request.args.get('direction', 'desc')
    ascending = True if direction == "asc" else False

    libs = pd.DataFrame()
    if os.path.isfile(current_app.config["LIB"]):
        libs = pd.read_csv(current_app.config["LIB"]).fillna("")
        libs.sort_values(by=column, ascending=ascending, inplace=True)

    return render_template("libraries.html", libs=libs, column=column, direction=direction)


@main_routes.route('/del_lib/<library_name>')
def del_library(library_name: str):
    path = os.path.join(current_app.config["LIBR"], library_name)
    try:
        libs = pd.read_csv(current_app.config["LIB"])
        used_in_raw = libs.loc[libs["library_name"]
                               == library_name, "used_in"].iloc[0]
        used_in = json.loads(used_in_raw)
        if used_in != []:  # if it still in use
            flash(("Library is still required by the programs: "
                   f"{', '.join(used_in)}. "
                   "To remove the entry from the libraries, "
                   "uninstall all programs using it. "
                   "Reinstalling is also possible."),
                  "warning")
            libs.loc[libs["library_name"] ==
                     library_name, "status"] = "deleted"
            flash(f"The entry of the library {library_name} is successfully deleted.",
                  "success")
        else:
            zip_loc = libs.loc[libs["library_name"] ==
                               library_name, "zip_path"].iloc[0]
            os.remove(zip_loc)
            libs = libs[libs["library_name"] != library_name]
        libs.to_csv(current_app.config["LIB"], index=False)

        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            flash(f"The library {library_name} is successfully deleted.",
                  "success")
        else:
            flash(f"The files of the library {library_name} have been already deleted.",
                  "warning")
    except Exception as err:
        msg = f"Error in deleting the library: {err}<br>"
        msg += f"Details:<br><pre>{traceback.format_exc()}</pre>"
        flash(msg, "warning")
    finally:
        return redirect(url_for("main_routes.libraries"))


@main_routes.route('/lib/<library_name>')
def get_lib(library_name):
    libs = pd.read_csv(current_app.config["LIB"])
    zip_path = libs.loc[libs["library_name"]
                        == library_name, "zip_path"].iloc[0]
    path_to_zip = os.path.join(current_app.config["LIB"], zip_path)
    orig_filename = libs.loc[libs["library_name"]
                             == library_name, "orig_filename"].iloc[0]

    return send_file(path_to_zip,
                     mimetype='main_routeslication/zip',
                     as_attachment=True,
                     download_name=orig_filename)


@main_routes.route('/check_status', methods=['POST'])
def check_status():
    # Get the current status sent by the client
    data_received = request.json
    activity_msg = data_received.get('status', ' ')
    prev_count = activity_msg.split()[0]
    # You can log or use this as required
    if "program" in activity_msg and os.path.isfile(current_app.config["PRG"]):
        data = pd.read_csv(current_app.config["PRG"])
        msg = activity(data, "programs")
    elif "run" in activity_msg and os.path.isfile(current_app.config["RUN"]):
        data = pd.read_csv(current_app.config["RUN"])
        msg = activity(data, "runs")
    else:
        return jsonify({'to_reload': False})

    curr_count = msg.split()[0]
    if prev_count == curr_count:
        return jsonify({'to_reload': False})

    return jsonify({'to_reload': True, "active_msg": msg})
