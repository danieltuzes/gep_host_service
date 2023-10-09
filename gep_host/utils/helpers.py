import os
import re
import subprocess
from datetime import datetime
import zipfile

import pandas as pd


def sanitize_name(name):
    """
    Convert the provided name to contain only English letters and underscores.
    """
    sanitized_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    return sanitized_name


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
    old_entries = pd.DataFrame()
    if os.path.isfile(filename):
        old_entries = pd.read_csv(filename)

    runs = pd.concat([old_entries, new_entry], ignore_index=True)
    runs.to_csv(filename, index=False)
