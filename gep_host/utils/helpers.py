import os
import subprocess
from datetime import datetime
import json
import zipfile
import tarfile

import pandas as pd


def alnum(name, extra_allowed="_"):
    return ''.join(e for e in name if e.isalnum() or e in extra_allowed)


def safer_call(name):
    return ''.join(e for e in name if e.isalnum() or e in """ '"-_/\\^()[],.""")


def concat_to(new_entry: pd.DataFrame, filename: str) -> None:
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


def name_to_html_id(filename, keep_extension=False):
    # Remove file extension
    if not keep_extension:
        filename = filename.rsplit('.', 1)[0]

    # Replace special characters with underscores and ensure it doesn't start with a number
    sanitized_id = ''.join(['_' + char if char.isdigit() and i == 0 else char if char.isascii()
                           and char.isalnum() else '_' for i, char in enumerate(filename)])

    return sanitized_id


def get_run_link(prg_name, purp, conf):
    """Get the link to the run in the frontend."""
    run_id = f"{name_to_html_id(prg_name, True)}__{purp}"
    port = "" if int(conf['port']) == 80 else f":{conf['port']}"
    link = f"http://{conf['host_name']}{port}/runs#{run_id}"
    return link
