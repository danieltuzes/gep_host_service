import os
import shutil
import subprocess
from configparser import ConfigParser

def copy_and_overwrite_files(src, dest):
    """
    Copies files from src to dest. Overwrites if already exists.
    """
    shutil.copytree(src, dest)

def setup_inputs(setup_folder, master_folder, uploaded_inputs, inherited_inputs):
    """
    Set up the inputs based on user selections and uploads.
    """
    inputs_tmp = os.path.join(setup_folder, 'inputs_tmp')
    inputs_folder = os.path.join(setup_folder, 'inputs')
    
    # Ensure inputs folder exists
    if not os.path.exists(inputs_folder):
        os.makedirs(inputs_folder)

    # Move all the uploaded files from inputs_tmp to inputs
    for file in os.listdir(inputs_tmp):
        shutil.move(os.path.join(inputs_tmp, file), os.path.join(inputs_folder, file))

    # Handle inheritance
    for input_name, filename in inherited_inputs.items():
        src = os.path.join(master_folder, 'config', filename)
        dest = os.path.join(inputs_folder, filename)
        shutil.copy(src, dest)

    # Update MasterConfig.cfg with the paths to the inputs
    config_path = os.path.join(setup_folder, 'MasterConfig.cfg')
    config = ConfigParser()
    config.read(config_path)
    for input_name, filename in uploaded_inputs.items():
        config.set('inputs', input_name, os.path.join(inputs_folder, filename))
    
    with open(config_path, 'w') as config_file:
        config.write(config_file)

def execute_program_in_conda_env(conda_env, module_name, user_cla, cwd):
    """
    Executes a program within a specified conda environment.
    """
    activate_env = f"source activate {conda_env}"
    run_command = f"python -m {module_name} {user_cla}"
    full_command = f"{activate_env} && {run_command}"

    with open(os.path.join(cwd, 'stdout.log'), 'w') as stdout_file, \
         open(os.path.join(cwd, 'stderr.log'), 'w') as stderr_file:
        
        process = subprocess.Popen(
            full_command, 
            shell=True,
            cwd=cwd,
            stdout=stdout_file, 
            stderr=stderr_file
        )
        process.communicate()

    return process.returncode

if __name__ == "__main__":
    # You'll have to pass arguments or set these values according to your needs.
    program_name = "example_program_name"
    user_cla = "--example_arg value"
    setup_name = "example_setup_name"

    # Paths
    master_folder = os.path.join('programs', program_name)
    setup_folder = os.path.join('runs', setup_name)

    # Step 1: Copy master folder to setup folder
    copy_and_overwrite_files(master_folder, setup_folder)

    # Step 2: Set up the inputs
    # You will need to retrieve or pass the uploaded_inputs and inherited_inputs
    uploaded_inputs = {
        'example_input': 'example_file.txt'
    }
    inherited_inputs = {
        'inherited_input': 'inherited_file.txt'
    }
    setup_inputs(setup_folder, master_folder, uploaded_inputs, inherited_inputs)

    # Step 3: Execute the program in the conda environment
    return_code = execute_program_in_conda_env(program_name, program_name, user_cla, setup_folder)

    # Step 4: Handle program end status
    status_file_path = None
    if return_code == 0:
        status_file_path = os.path.join(setup_folder, 'success')
    else:
        status_file_path = os.path.join(setup_folder, 'error')
        with open(status_file_path, 'w') as status_file:
            status_file.write(str(return_code))
