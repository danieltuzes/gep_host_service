from pathlib import Path
import json
import datetime
import os
import shutil
from configparser import ConfigParser, ExtendedInterpolation
import traceback
import zipfile
import platform
import multiprocessing

from flask import render_template, request, redirect, flash, url_for, send_from_directory, send_file
import pandas as pd
from werkzeug.utils import secure_filename

from gep_host import app, install_program, delete_program, delete_run, run_program
zipdir = run_program.zipdir

PROJ_ROOT = Path(os.path.dirname(__file__)).parent.parent
PROGRAM_DETAILS_CSV = os.path.join(PROJ_ROOT,
                                   'programs/program_details.csv')
RUN_DETAILS_CSV = os.path.join(PROJ_ROOT, 'runs/run_details.csv')
LIB_DETAILS_CSV = os.path.join(PROJ_ROOT, 'libs/lib_details.csv')


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'zip'


def alnum(name, extra_allowed="_"):
    return ''.join(e for e in name if e.isalnum() or e in extra_allowed)


def safer_call(name):
    return ''.join(e for e in name if e.isalnum() or e in """ '"-_/\\^()[],.""")


@app.route('/')
def index():
    data = {
        'System': platform.system(),
        'Node': platform.node(),
        'Release': platform.release(),
        'Version': platform.version(),
        'Machine': platform.machine(),
        'Architecture': platform.architecture()[0],
        'Processor': platform.processor(),
        'Number of Cores': multiprocessing.cpu_count()
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


@app.route('/programs', methods=['GET', 'POST'])
def programs():
    if request.method == 'POST':
        # Logic for handling the file upload
        if 'program_package' not in request.files:
            flash('No file part', 'warning')
            return redirect(request.url)
        file = request.files['program_package']
        if file.filename == '':
            flash('No selected file', 'warning')
            return redirect(request.url)
        if not allowed_file(file.filename):
            flash('Not allowed filetype', 'warning')
            return redirect(request.url)

        # Program details
        program_name = alnum(request.form['unique_program_name'])
        python_version_raw = request.form['required_python_version']
        python_version = "".join(
            char for char in python_version_raw if char.isdigit or char == ".")
        selected_libs = request.form.getlist('selected_libs')

        # Check uniqueness of program name
        masterfolder = os.path.join(PROJ_ROOT, "programs", program_name)
        if os.path.isdir(masterfolder):
            flash('Program upload is unsuccessful due to its non-unique name.', 'warning')
            return redirect(request.url)

        # save the file
        filename = secure_filename(file.filename)
        base, ext = os.path.splitext(filename)
        nowstr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        t_filename = f"{base}_{nowstr}{ext}"
        program_zip_path = os.path.join(
            app.config['UPLOAD_FOLDER'], t_filename)
        file.save(program_zip_path)

        # Execute install script in subprocess
        res = install_program.init_install(program_name,
                                           t_filename,
                                           python_version,
                                           selected_libs)
        if res != 0:
            flash(res, "warning")
        else:
            flash('Program install started', 'success')

        return redirect(url_for('programs'))

    column = request.args.get('column', 'upload_date')
    direction = request.args.get('direction', 'desc')
    if os.path.exists(PROGRAM_DETAILS_CSV):
        df = pd.read_csv(PROGRAM_DETAILS_CSV, dtype=str).fillna("")
        ascending = True if direction == "asc" else False
        df.sort_values(by=column, ascending=ascending, inplace=True)
    else:
        df = pd.DataFrame()

    libs = pd.DataFrame()
    if os.path.isfile(LIB_DETAILS_CSV):
        libs = pd.read_csv(LIB_DETAILS_CSV)

    return render_template('programs.html',
                           programs=df,
                           libs=libs,
                           column=column,
                           direction=direction)


@app.route('/install_log/<program_name>')
def install_log(program_name: str):
    log_path = os.path.join(PROJ_ROOT, "programs", program_name)
    if os.path.isfile(log_path):
        return send_from_directory(log_path, "output_and_error.log")
    else:
        flash(("The log file has been already removed. "
              "Service integritiy is compromised. Notify the admin."), "warning")
        return programs()


@app.route('/del_program/<program_name>')
def del_program(program_name: str):
    exitcode, stdout = delete_program.init_del(program_name)
    if exitcode != 0:
        flash(f"Couldn't fully delete {program_name}. Details:<br><pre>{stdout}</pre>",
              "warning")
    else:
        flash(f"Successfully deleted program: {program_name}", "success")
    return programs()


@app.route('/program/<program_name>')
def get_prg(program_name: str):
    prgs = pd.read_csv(PROGRAM_DETAILS_CSV)
    zip_fname = prgs.loc[prgs["program_name"]
                         == program_name, "zip_fname"].iloc[0]
    f_path = os.path.join(PROJ_ROOT, "programs", zip_fname)
    orig_fname = zip_fname[:-19] + zip_fname[-4:]

    return send_file(f_path,
                     mimetype='application/zip',
                     as_attachment=True,
                     download_name=orig_fname)


@app.route('/runs', methods=['GET', 'POST'])
def runs():
    column = request.args.get('column', 'setup_date')
    direction = request.args.get('direction', 'desc')
    program_name = request.args.get('program_name')

    if request.method == 'POST':
        # check if the purpose is unique
        program_name = request.form["program_name"]
        purpose = alnum(request.form["purpose"])
        python_args = safer_call(request.form["args"])
        setup_folder = os.path.join(PROJ_ROOT, "runs", program_name, purpose)
        if os.path.isdir(setup_folder):
            flash('Run setup is unsuccessful due to its non-unique purpose.', 'warning')
            return redirect(request.url)

        # copy the program to a new location
        masterfolder = os.path.join(PROJ_ROOT, "programs", program_name)
        shutil.copytree(masterfolder, setup_folder)

        # save all the inputs
        prgs = pd.read_csv(PROGRAM_DETAILS_CSV, dtype=str)
        inputs = json.loads(prgs.loc[prgs.program_name == program_name,
                                     "inputs"].iloc[0])
        input_folder = os.path.join(setup_folder, "inputs")
        os.makedirs(input_folder, exist_ok=True)
        inherits = []
        uploads = []
        for input in inputs:
            # skip if inherited
            if input[1] is not None:
                checkbox_value = request.form.get(f'check{input[0]}')
                if checkbox_value:
                    inherits.append(input)
                    continue

            # skip if not provided
            file = request.files[input[0]]
            fname = secure_filename(file.filename)
            if fname != "":
                file.save(os.path.join(input_folder, fname))
                input[1] = os.path.join("inputs", fname)

            uploads.append(input)

        # update the config
        config_file = os.path.join(setup_folder, 'config', 'MasterConfig.cfg')
        config = ConfigParser(os.environ,
                              interpolation=ExtendedInterpolation())
        config.read(config_file)
        if 'Root' in config and 'RootDir' in config['Root']:
            config.set('Root', 'RootDir', setup_folder)
            config["DEFAULT"] = {}
        for upload in uploads:
            if upload[1] is not None:
                uploaded_path = os.path.join(setup_folder, upload[1])
                config.set('inputs', upload[0], uploaded_path)
        outputs = []
        for ofile in config.options("outputs"):
            ofilepath = os.path.relpath(config.get("outputs", ofile),
                                        setup_folder)
            outputs.append([ofile, ofilepath])
        with open(config_file, 'w') as configfile:
            config.write(configfile)

        new_entry = pd.DataFrame({
            'program_name': [program_name],
            'purpose': [purpose],
            'python_args': [python_args],
            'setup_date': [datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
            'status': ['set up'],
            'uploaded_files': [json.dumps(uploads)],
            'inherited_files': [json.dumps(inherits)],
            'outputs': [json.dumps(outputs)],
            'comment': request.form["comment"],
            'notifications': request.form["notifications"]
        })

        runs = pd.DataFrame({})
        if os.path.isfile(RUN_DETAILS_CSV):
            runs = pd.read_csv(RUN_DETAILS_CSV)

        runs = pd.concat([runs, new_entry], ignore_index=True)
        runs.to_csv(RUN_DETAILS_CSV, index=False)

        run_program.init_run(program_name, purpose)
        flash("Program set up and run initiated successfully.", "success")

    # Read the content of run_details.csv, filter and order it

    if os.path.exists(RUN_DETAILS_CSV):
        runs = pd.read_csv(RUN_DETAILS_CSV, dtype=str).fillna("")

        # order
        ascending = True if direction == "asc" else False
        runs.sort_values(by=column, ascending=ascending, inplace=True)

        # filter
        if program_name is not None:
            runs = runs[runs["program_name"] == program_name]
    else:
        runs = pd.DataFrame()

    if os.path.exists(PROGRAM_DETAILS_CSV):
        prgs = pd.read_csv(PROGRAM_DETAILS_CSV, dtype=str)
    else:
        prgs = pd.DataFrame()

    inputs = []
    if program_name is not None:
        inputs = prgs.loc[prgs.program_name == program_name, "inputs"].iloc[0]
        inputs = json.loads(inputs)

    return render_template('runs.html',
                           runs=runs,
                           program_name=program_name,
                           inputs=inputs,
                           direction=direction,
                           column=column)


@app.route('/users_tokens')
def users_tokens():
    return render_template('users_tokens.html')


@app.route('/program/<program_name>/<input_value>')
def get_program_input(program_name, input_value):
    f_path = os.path.join(PROJ_ROOT, "programs", program_name, input_value)
    return send_from_directory(os.path.dirname(f_path),
                               os.path.basename(f_path))


@app.route('/run/<program_name>/<purpose>/<file>')
def get_run_file(program_name, purpose, file):
    f_path = os.path.join(PROJ_ROOT,
                          "runs",
                          program_name,
                          purpose,
                          file)
    return send_from_directory(os.path.dirname(f_path), os.path.basename(f_path))


@app.route('/del_run/<program_name>/<purpose>')
def del_run(program_name: str, purpose: str):
    exitcode, stdout = delete_run.init_del(program_name, purpose)
    if exitcode != 0:
        msg = "<pre>" + stdout + "</pre>"
        flash(f"Couldn't fully delete {program_name} with purpose {purpose}. Details:<br>{msg}",
              "warning")
    else:
        flash(
            f"Successfully deleted program {program_name} with purpose {purpose}", "success")
    return runs()


@app.route('/run_log/<program_name>/<purpose>')
def run_log(program_name: str, purpose: str):
    log_path = os.path.join(PROJ_ROOT, "runs", program_name, purpose)
    return send_from_directory(log_path, "output_and_error.log")


@app.route('/libraries', methods=['GET', 'POST'])
def libraries():
    column = request.args.get('column', 'upload_date')
    direction = request.args.get('direction', 'desc')
    ascending = True if direction == "asc" else False

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
        path_to_exec = request.form['path_to_exec']

        # Check uniqueness of library name
        masterfolder = os.path.join(PROJ_ROOT, "libs", library_name)
        if os.path.isdir(masterfolder):
            flash('Library upload is unsuccessful due to its non-unique name.', 'warning')
            return redirect(request.url)

        # save the file
        filename = secure_filename(file.filename)
        base, ext = os.path.splitext(filename)
        nowstr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        t_filename = f"{base}_{nowstr}{ext}"
        program_zip_path = os.path.join(PROJ_ROOT, "libs", t_filename)
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
            return render_template("libraries.html", libs=libs, column=column)

        nowstr = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
            'zip_path': [os.path.relpath(program_zip_path, PROJ_ROOT)],
            'orig_filename': [filename],
            'status': ["installed"],
            'size': [file_size_str],
            'comment': request.form["comment"],
            'used_in': [json.dumps([])]
        })

        libs = pd.DataFrame()
        if os.path.isfile(LIB_DETAILS_CSV):
            libs = pd.read_csv(LIB_DETAILS_CSV)
        libs = pd.concat([libs, new_entry], ignore_index=True)
        libs.to_csv(LIB_DETAILS_CSV, index=False)
        flash(f"Library {library_name} is successfully uploaded.", "success")

    libs = pd.DataFrame()
    if os.path.isfile(LIB_DETAILS_CSV):
        libs = pd.read_csv(LIB_DETAILS_CSV).fillna("")
        libs.sort_values(by=column, ascending=ascending, inplace=True)

    return render_template("libraries.html", libs=libs, column=column, direction=direction)


@app.route('/del_lib/<library_name>')
def del_library(library_name: str):
    path = os.path.join(PROJ_ROOT, "libs", library_name)
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            flash(
                f"Library {library_name} is successfully deleted.", "success")
        else:
            flash(
                f"Library {library_name} has been already deleted.", "warning")
        libs = pd.read_csv(LIB_DETAILS_CSV)
        used_in_raw = libs.loc[libs["library_name"]
                               == library_name, "used_in"].iloc[0]
        used_in = json.loads(used_in_raw)
        if used_in != []:
            flash(("Library is still required by the programs: "
                   f"{', '.join(used_in)}. "
                   "To remove the entry from the libraries, "
                   "uninstall all programs using it. "
                   "Reinstalling is also possible."),
                  "warning")
            libs.loc[libs["library_name"] ==
                     library_name, "status"] = "deleted"
        else:
            zip_loc = libs.loc[libs["library_name"] ==
                               library_name, "zip_path"].iloc[0]
            os.remove(zip_loc)
            libs = libs[libs["library_name"] != library_name]
        libs.to_csv(LIB_DETAILS_CSV, index=False)
    except Exception as err:
        msg = f"Error in deleting the library: {err}<br>"
        msg += f"Details:<br><pre>{traceback.format_exc()}</pre>"
        flash(msg, "warning")
    finally:
        return libraries()


@app.route('/lib/<library_name>')
def get_lib(library_name):
    libs = pd.read_csv(LIB_DETAILS_CSV)
    zip_path = libs.loc[libs["library_name"]
                        == library_name, "zip_path"].iloc[0]
    path_to_zip = os.path.join(PROJ_ROOT, zip_path)

    orig_filename = libs.loc[libs["library_name"]
                             == library_name, "orig_filename"].iloc[0]
    f_path = os.path.join(PROJ_ROOT,
                          "libs",
                          path_to_zip)
    return send_file(f_path,
                     mimetype='application/zip',
                     as_attachment=True,
                     download_name=orig_filename)


def parse_json(json_str):
    if isinstance(json_str, str) and json_str != "":
        return json.loads(json_str)
    return []


app.jinja_env.filters['parse_json'] = parse_json
