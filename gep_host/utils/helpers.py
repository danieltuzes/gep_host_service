import os
import subprocess
from datetime import datetime
import json
import zipfile
import tarfile

import pandas as pd


def check_unique_program_name(program_name):
    """
    Check if the program name is unique in program_details.csv
    """
    df = pd.read_csv('programs/program_details.csv')
    return program_name not in df['program_name'].values


def update_program_details_csv(program_name, python_version, status='uploaded'):
    """
    Update or Add a new entry to program_details.csv
    """
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    data = {
        'program_name': program_name,
        'upload_date': now,
        'python_version': python_version,
        'note': status
    }
    df = pd.read_csv('programs/program_details.csv')
    df = df.append(data, ignore_index=True)
    df.to_csv('programs/program_details.csv', index=False)


def run_subprocess(command, cwd=None):
    """
    Run a subprocess with the provided command.
    """
    process = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = process.communicate()
    return process.returncode, stdout, stderr


def append_to_filename(filename, append_string):
    """
    Append a string to the filename before its extension.
    """
    base, ext = os.path.splitext(filename)
    return f"{base}_{append_string}{ext}"


def get_current_datetime_string():
    """
    Returns the current date and time as a string in the format 'YYYYMMDD_HHMMSS'.
    """
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def check_unique_run_name(setup_name):
    """
    Check if the run setup name is unique within the runs folder.
    """
    return not os.path.exists(os.path.join('runs', setup_name))


def alnum(name, extra_allowed="_"):
    return ''.join(e for e in name if e.isalnum() or e in extra_allowed)


def safer_call(name):
    return ''.join(e for e in name if e.isalnum() or e in """ '"-_/\\^()[],.""")


def concat_to(new_entry: pd.DataFrame, filename: pd.DataFrame) -> None:
    """Add new entry/entries to file, create if doesn't exist."""
    old_entries = pd.read_csv(filename)
    runs = pd.concat([old_entries, new_entry], ignore_index=True)
    runs.to_csv(filename, index=False)


def remove_readonly(path):
    """Recursively remove read-only attributes from files and directories."""
    for root, dirs, files in os.walk(path):
        for name in files:
            os.chmod(os.path.join(root, name), 0o666)
        for name in dirs:
            os.chmod(os.path.join(root, name), 0o777)


def remove_val_from_json(json_str, val_2_remove):
    mylist = json.loads(json_str)
    new_list = [val for val in mylist if val != val_2_remove]
    return json.dumps(new_list)


def extract_file(file_data, extract_path) -> bool:
    """
    Extracts the contents of a zip or tar file to the specified directory.

    Parameters
    ----------
    file_data : str
        The path to the zip or tar file.
    extract_path : str
        The directory where the contents will be extracted.

    Returns
    -------
    bool
        True if the extraction is successful, False otherwise.
    """
    if zipfile.is_zipfile(file_data):
        with zipfile.ZipFile(file_data) as zf:
            zf.extractall(extract_path)
    elif tarfile.is_tarfile(file_data):
        with tarfile.open(file_data, 'r:*') as tf:
            members = tf.getmembers()
            # Check if there is only one root directory
            root_dirs = {m.name.split('/')[0]
                         for m in members if '/' in m.name}
            if len(root_dirs) == 1:
                root_dir = root_dirs.pop() + '/'
                for member in members:
                    if member.name.startswith(root_dir):
                        # Remove the root directory from the path
                        member.name = member.name[len(root_dir):]
                        tf.extract(member, extract_path)
            else:
                tf.extractall(extract_path)
    else:
        return False
    return True


def get_orig_fname(zip_fname: str) -> str:
    """
    Return the original filename from a zip filename.

    Parameters
    ----------
    zip_fname : str
        The zip filename.

    Returns
    -------
    str
        The original filename without the timestamp.
    """
    if zip_fname.endswith(".zip"):
        orig_fname = zip_fname[:-19] + zip_fname[-4:]  # remove timestamp
    else:
        orig_fname = zip_fname[:-22] + zip_fname[-7:]
    return orig_fname


def filename_to_html_id(filename):
    # Remove file extension
    name_without_ext = filename.rsplit('.', 1)[0]

    # Replace special characters with underscores and ensure it doesn't start with a number
    sanitized_id = ''.join(['_' + char if char.isdigit() and i == 0 else char if char.isascii()
                           and char.isalnum() else '_' for i, char in enumerate(name_without_ext)])

    return sanitized_id
