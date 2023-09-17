from pathlib import Path
import json
import datetime
import os
import shutil
from configparser import ConfigParser, ExtendedInterpolation

from flask import render_template, request, redirect, flash, url_for, send_from_directory
import pandas as pd
from werkzeug.utils import secure_filename

from gep_host import app, install_program, delete_program, delete_run, run_program

PROJ_ROOT = Path(os.path.dirname(__file__)).parent.parent
PROGRAM_DETAILS_CSV = os.path.join(PROJ_ROOT,
                                   'programs/program_details.csv')
RUN_DETAILS_CSV = os.path.join(PROJ_ROOT, 'runs/run_details.csv')


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'zip'


def alnum(name):
    return ''.join(e for e in name if e.isalnum() or e == '_')


def safer_call(name):
    return ''.join(e for e in name if e.isalnum() or e in """ '"-_/\\^()[],.""")


@app.route('/')
def index():
    return render_template('index.html')


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
        python_version = request.form['required_python_version']

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
                                           program_zip_path,
                                           python_version)
        if res != 0:
            flash(res, "warning")
        else:
            flash('Program install started', 'success')

        return redirect(url_for('programs'))

    column = request.args.get('column', 'upload_date')
    direction = request.args.get('direction', 'desc')
    if os.path.exists(PROGRAM_DETAILS_CSV):
        df = pd.read_csv(PROGRAM_DETAILS_CSV)
        ascending = True if direction == "asc" else False
        df.sort_values(by=column, ascending=ascending, inplace=True)
    else:
        df = pd.DataFrame()
    return render_template('programs.html', programs=df, column=column, direction=direction)


@app.route('/install_log/<program_name>')
def install_log(program_name: str):
    log_path = os.path.join(PROJ_ROOT, "programs", program_name)
    return send_from_directory(log_path, "output_and_error.log")


@app.route('/del_program/<program_name>')
def del_program(program_name: str):
    exitcode, stdout = delete_program.init_del(program_name)
    if exitcode != 0:
        flash(f"Couldn't fully delete {program_name}. Details:<br><pre>{stdout}</pre>",
              "warning")
    else:
        flash(f"Successfully deleted program: {program_name}", "success")
    return programs()


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
            if fname == "":
                continue

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

        if os.path.isfile(RUN_DETAILS_CSV):
            runs = pd.read_csv(RUN_DETAILS_CSV)
        else:
            runs = pd.DataFrame({})
        runs = pd.concat([runs, new_entry], ignore_index=True)
        runs.to_csv(RUN_DETAILS_CSV, index=False)

        run_program.init_run(program_name, purpose)
        flash("Program set up and run initiated successfully.", "success")

    # Read the content of run_details.csv, filter and order it

    if os.path.exists(RUN_DETAILS_CSV):
        runs = pd.read_csv(RUN_DETAILS_CSV, dtype=str)
        runs.fillna("", inplace=True)

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
    return send_from_directory(os.path.dirname(f_path), os.path.basename(f_path))


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


def parse_json(json_str):
    if isinstance(json_str, str) and json_str != "":
        return json.loads(json_str)
    return []


@app.route('/run_log/<program_name>/<purpose>')
def run_log(program_name: str, purpose: str):
    log_path = os.path.join(PROJ_ROOT, "runs", program_name, purpose)
    return send_from_directory(log_path, "output_and_error.log")


app.jinja_env.filters['parse_json'] = parse_json