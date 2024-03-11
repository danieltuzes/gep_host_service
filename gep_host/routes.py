import json
from datetime import datetime
import os
import shutil
from configparser import ConfigParser, ExtendedInterpolation
import traceback
import platform
import multiprocessing
import logging
import hashlib
from io import StringIO
from typing import List

from flask import render_template, request, redirect, flash, \
    url_for, send_from_directory, send_file, Response, jsonify, Blueprint, current_app
import pandas as pd
from markupsafe import Markup
from werkzeug.utils import secure_filename
import psutil
import markdown

from .utils import install_program, delete_program, delete_run, run_program
from .utils.helpers import *
from . import __version__


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
    return '.' in filename and (filename.endswith('.zip') or filename.endswith('.tar.gz'))


@main_routes.route('/')
def index():
    sorted_config = dict(sorted(current_app.config.items(),
                         key=lambda k: (k[0][0].isupper(), k[0])))
    service_config = {"version": __version__, **sorted_config}

    data = {
        'System': platform.system(),
        'Node': platform.node(),
        'Release': platform.release(),
        'Version': platform.version(),
        'Machine': platform.machine(),
        'Architecture': platform.architecture()[0],
        'Processor': platform.processor(),
        'Number of Cores': multiprocessing.cpu_count(),
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

    readme_path = os.path.join(os.path.dirname(__file__), '..', 'README.md')
    with open(readme_path, 'r') as f:
        content = f.read()

    # Convert markdown to HTML
    md_template = Markup(markdown.markdown(content, extensions=['toc']))

    return render_template('index.html',
                           md_template=md_template,
                           data=data,
                           service_config=service_config)


@main_routes.route('/programs', methods=['GET'])
def programs():
    """Show programs, confirm successful installation."""
    column = request.args.get('column', 'upload_date')
    direction = request.args.get('direction', 'desc')
    prgs = pd.read_csv(current_app.config["PRG"], dtype=str).fillna("")
    ascending = True if direction == "asc" else False
    prgs.sort_values(by=column, ascending=ascending, inplace=True)
    libs = pd.read_csv(current_app.config["LIB"]).sort_values(
        by="upload_date", ascending=False)

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
        flash('No selected package file or git source', 'warning')
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
        return redirect(url_for("main_routes.programs"))

    # save the file or pass git source
    git = {}
    if file.filename == "":
        filename = f"{program_name}.zip"
        git["git-source-url"] = request.form["git-source-url"].strip()
        git["git-source-ref"] = request.form["git-source-ref"].strip()
    else:
        filename = secure_filename(file.filename)
    base, ext = os.path.splitext(filename)
    if ext == '.gz' and base.endswith('.tar'):
        ext = '.tar.gz'
        base = base[:-4]
    nowstr = datetime.now().strftime('%Y%m%d%H%M%S')
    t_filename = f"{base}_{nowstr}{ext}"
    program_zip_path = os.path.join(current_app.config['PRGR'], t_filename)
    if file.filename != "":
        file.save(program_zip_path)

    # Execute install script in subprocess
    res = install_program.init_install(program_name,
                                       t_filename,
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
    orig_fname = get_orig_fname(zip_fname)

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
    runs = pd.read_csv(current_app.config["RUN"], dtype=str).fillna("")

    # order
    ascending = True if direction == "asc" else False
    runs.sort_values(by=column, ascending=ascending, inplace=True)

    # filter
    if program_name is not None:
        runs = runs[runs["program_name"] == program_name]

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


def setup_dynamic_routes(config):
    for page_key, page_name in config.items():
        create_dynamic_route(page_key)


def create_dynamic_route(page_key):
    @main_routes.route(f'/{page_key}', endpoint=page_key)
    def dynamic_route():
        return render_template(f'{page_key}.html')

    dynamic_route.__name__ = page_key  # Ensures the function name is unique


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
            if not extract_file(program_zip_path, masterfolder):
                raise Exception("The library is not a zip of tar.gz file.")
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

        libs = pd.DataFrame()
        used_in = json.dumps([])
        libs = pd.read_csv(current_app.config["LIB"])
        prev_entry = libs.loc[libs["library_name"] == library_name]
        if not prev_entry.empty:
            used_in = prev_entry["used_in"].iloc[0]
            libs = libs.loc[libs["library_name"] != library_name]

        new_entry = pd.DataFrame({
            'library_name': [library_name],
            'path_to_exec': [path_to_exec],
            'upload_date': [nowstr],
            'zip_path': [os.path.relpath(program_zip_path, current_app.config["ROOT"])],
            'orig_filename': [filename],
            'status': ["Installed"],
            'size': [file_size_str],
            'comment': request.form["comment"],
            'used_in': [used_in]
        })

        libs = pd.concat([libs, new_entry], ignore_index=True)
        libs.to_csv(current_app.config["LIB"], index=False)
        flash(f"Library {library_name} is successfully uploaded.", "success")
        return redirect(url_for("main_routes.libraries"))

    column = request.args.get('column', 'upload_date')
    direction = request.args.get('direction', 'desc')
    ascending = True if direction == "asc" else False

    libs = pd.read_csv(current_app.config["LIB"]).fillna("")
    libs.sort_values(by=column, ascending=ascending, inplace=True)

    return render_template("libraries.html", libs=libs, column=column, direction=direction)


@main_routes.route('/del_lib/<library_name>')
def del_library(library_name: str):
    try:
        libs = pd.read_csv(current_app.config["LIB"])
        used_in_raw = libs.loc[libs["library_name"]
                               == library_name, "used_in"].iloc[0]
        used_in = json.loads(used_in_raw)
        if used_in != []:  # if it still in use
            flash(("The library's entry stays with a mark deleted, "
                   "because programs are still using it: "
                   f"{', '.join(used_in)}. "
                   "To remove the entry from the libraries, "
                   "uninstall all programs using it. "
                   "Reinstalling is also possible."),
                  "warning")
            libs.loc[libs["library_name"] ==
                     library_name, "status"] = "deleted"
        else:
            zip_path = libs.loc[libs["library_name"] ==
                                library_name, "zip_path"].iloc[0]
            zip_loc = os.path.join(current_app.config["ROOT"], zip_path)
            os.remove(zip_loc)
            libs = libs[libs["library_name"] != library_name]
        libs.to_csv(current_app.config["LIB"], index=False)

        path = os.path.join(current_app.config["LIBR"], library_name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            if used_in != []:
                flash(f"The files associated with the library {library_name} "
                      "is successfully deleted.",
                      "success")
            else:
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
    path_to_zip = os.path.join(current_app.config["ROOT"], zip_path)
    orig_filename = libs.loc[libs["library_name"]
                             == library_name, "orig_filename"].iloc[0]

    return send_file(path_to_zip,
                     mimetype='main_routeslication/zip',
                     as_attachment=True,
                     download_name=orig_filename)


@main_routes.route('/files', methods=['GET'])
def upload_form():
    column = request.args.get('column', 'upload_date')
    direction = request.args.get('direction', 'desc')

    df = pd.read_csv(current_app.config['FLE'])

    if direction == 'desc':
        df = df.sort_values(by=column, ascending=False)
    else:
        df = df.sort_values(by=column, ascending=True)

    return render_template('upload.html', files=df, column=column, direction=direction)


@main_routes.route('/save_files', methods=['POST'])
def save_files():
    uploaded_files = [f for f in request.files.values()]
    data = []
    new_filenames = []

    csv_path = current_app.config['FLE']
    df = pd.read_csv(csv_path)

    comment = request.form.get("comment")
    for file in uploaded_files:
        if file:
            # Save file with datestring added to filename
            secure_fname = secure_filename(file.filename)
            file_content = file.read()
            file_hash = hashlib.md5(file_content).hexdigest()
            file.seek(0)

            filename, file_extension = os.path.splitext(secure_fname)
            new_filename = f"{filename}_{file_hash[:8]}{file_extension}"
            now = datetime.now()

            filepath = os.path.join(current_app.config['FLSR'], new_filename)
            matches = df.loc[df["hash"] == file_hash]
            if len(matches):
                other_fname = matches["filename"].iloc[0]
                flash(f"File named {file.filename} has the same content as "
                      f"{other_fname}. This file is not saved.",
                      "warning")
                continue
            file.save(filepath)

            # Calculate file size and hash
            size = len(file_content)

            # Save file details to CSV
            data.append({
                "filename": new_filename,
                "upload_date": now.strftime('%Y-%m-%d %H:%M:%S'),
                "size": size,
                "hash": file_hash,
                "comment": comment,
                "used_in": "[]"
            })
            new_filenames.append(new_filename)

    if len(new_filenames):
        flash(f"{len(new_filenames)} file(s) are successfully saved: "
              f"{', '.join(new_filenames)}", "success")

    df = pd.concat([df, pd.DataFrame(data)], ignore_index=True)
    df.to_csv(csv_path, index=False)

    return jsonify({"success": True, "message": "Files uploaded successfully"})


@main_routes.route('/get_file', methods=['GET'])
def get_file():
    filename_full = request.args.get('filename')
    directory, filename = os.path.split(filename_full)
    csv_path = current_app.config['FLE']
    df = pd.read_csv(csv_path)
    matches = df.loc[df["filename"] == filename, "dir"]
    if matches.empty:
        return "File not found in the database", 404
    m_dir = matches.iloc[0]
    if pd.isna(m_dir):
        location = os.path.join(current_app.config["FLSR"], filename)
    else:
        location = os.path.join(directory, filename)
    if os.path.isfile(location):
        return send_file(location,
                         as_attachment=True,
                         download_name=filename)
    else:
        return "File not found in the system", 404


@main_routes.route('/delete_file', methods=['GET'])
def delete_file():
    filename = request.args.get('filename')

    # check if file is in database
    csv_path = current_app.config['FLE']
    df = pd.read_csv(csv_path)
    matches = df['filename'] == filename
    if not matches.any():
        return jsonify({"message": "File not found in the database"}), 404

    # remove from database
    updated_df = df[~matches]
    updated_df.to_csv(csv_path, index=False)

    # detect of the file was just registered
    if os.path.sep in filename or "/" in filename:
        return jsonify({"message": "File is unregistered"}), 200

    # Remove the file from the file system
    file_path = os.path.join(current_app.config['FLSR'], filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return jsonify({"message": "File successfully deleted"}), 200
    else:
        return jsonify({"message": "File not found on the server, so the entry is removed"}), 200


@main_routes.route('/register_files', methods=['POST'])
def register_files():
    data = request.get_json()
    locals = data.get('local')
    pattern = r'\".*?\"|\S+'
    filenames: List[str] = re.findall(pattern, locals)

    # Clean up the filenames: remove quotation marks
    success_message = ""
    warning_message = ""
    for local in filenames:
        local = local.strip('"')
        if not os.path.isfile(local):
            warning_message += f"File {local} is not found on the server.\n"
            continue

        csv_path = current_app.config['FLE']
        df = pd.read_csv(csv_path)
        directory, filename = os.path.split(local)
        if (df["filename"] == filename).any():
            warning_message += f"Filename {local} is already registered.\n"
            continue

        size = os.path.getsize(local)
        comment = data.get('comment')
        new_entry = {"filename": filename,
                     "upload_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                     "size": size,
                     "comment": comment,
                     "dir": directory,
                     "used_in": "[]"}

        df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
        df.to_csv(csv_path, index=False)

        success_message += f"File {local} is successfully registered.\n"

    if success_message:
        flash(success_message, "success")
        if warning_message:
            flash(warning_message, "warning")

        return jsonify({"message": warning_message + "\n\n" + success_message}), 200

    return jsonify({"message": warning_message}), 400


@main_routes.route('/check_status', methods=['POST'])
def check_status():
    # Get the current status sent by the client
    data_received = request.json
    activity_msg = data_received.get('status', ' ')
    prev_count = activity_msg.split()[0]
    # You can log or use this as required
    if "program" in activity_msg:
        data = pd.read_csv(current_app.config["PRG"])
        msg = activity(data, "programs")
    elif "run" in activity_msg:
        data = pd.read_csv(current_app.config["RUN"])
        msg = activity(data, "runs")
    else:
        return jsonify({'to_reload': False})

    curr_count = msg.split()[0]
    if prev_count == curr_count:
        return jsonify({'to_reload': False})

    return jsonify({'to_reload': True, "active_msg": msg})
