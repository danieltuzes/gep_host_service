# GEP host service

- [Features](#features)
  - [Requirements on the program](#requirements-on-the-program)
    - [Additional features](#additional-features)
  - [Library installation](#library-installation)
  - [File upload and registration](#file-upload-and-registration)
  - [Running a program](#running-a-program)
- [Installing the webservice](#installing-the-webservice)
- [Configuring the webservice](#configuring-the-webservice)
- [Starting the service](#starting-the-service)
- [Known limitations](#known-limitations)

Execute data-oriented python scripts from a web interface. You can store different programs, and multiple runs of these programs, and all your inputs and outputs will be available for download via a web browser. No more python installation and manual config editing for program executors, saving developers from providing support.

## Features

You can add a python program, store libraries (provided from a zipped file to be used in runs) and files, each managed from its own tab in the web UI.

### Requirements on the program

The programs must meet specific design requirements:

1. The program must be directly callable or installable with a `pip install .` issued in the root, otherwise, the `requirements.txt` will be installed only.
2. The files and their paths are defined in a python ini file at `config/MasterConfig.cfg`, stored under the sections inputs and outputs.
3. Must be executable with a single command from `python`, e.g. `python -m my_module`.
4. Outputs must be saved within the root folder.

#### Additional features

1. Provide the version information in the `__main__.py` or `__init__.py`, and the version info will be shown for the package. Every module within the root and 1 level lower are searched for module and version values.
2. A git repo can be cloned instead of uploading a zip file, at a given branch, tag or commit hash. The user running the webservice must have access to the repo with no additional credentials being entered. Git submodules are all initiated.
3. The program's own `README.md` is rendered (with syntax-highlighted code blocks) on its details page.

### Library installation

Dependencies of the programs which cannot be installed via pip can be manually installed under the tab Libraries. When a new program is installed, during installation, the library can be selected. The webservice then creates a conda environment for the program, and puts the library's executable's path into that conda environment's `PATH`.

### File upload and registration

To share the same file over multiple runs, and to use local files, files can be registered under the tab Files.

### Running a program

Each run is identified by a program name and a purpose (a name you give the run). When triggered, a run is queued and executed with its own copy of the program's input files; its position in the queue is shown and kept up to date as earlier runs finish. From the Runs tab you can:

- follow the live output/error log of a run,
- stop a run that is currently executing,
- download a zip of a run's setup, inputs and outputs,
- get notified by email, at addresses you provide, once a run finishes.

## Installing the webservice

Install the library from source code by issuing `pip install .` in the root. For development, install the requirements too (`pip install -r requirements.txt`).

## Configuring the webservice

The service is configured through two ini files:

- `config/MasterConfig.cfg` — points to the settings file and to `HostRoot`, the directory where installed programs, runs, libraries, files and logs are stored.
- `config/host.cfg` (referenced from the master config as `Settings`) — the service name, port, host, static page definitions and other display settings such as the email pattern used to validate notification addresses.

Copy and adjust these files for your deployment, then point `--master_config` at your copy (see below).

## Starting the service

- For production, run `python -m gep_host`
- For debugging, run `python -m gep_host --debug`
- By default, `config/MasterConfig.cfg` (relative to the working directory) is used; pass a different file with `python -m gep_host --master_config path/to/MasterConfig.cfg`

## Known limitations

- User accounts and access tokens are not implemented yet: every visitor currently has full access, including deleting programs, runs and libraries, and downloading files that would otherwise be marked as non-public.
- A queued run cannot be cancelled before it starts; only an already-running one can be stopped.

See the roadmap notes in this file's source for further planned improvements.

<!--
- if masterinput fails, show the run setup so it can be deleted or delete it
- comments are not saved for registered file
- re is not imported in routes.py?
- UX: Problem: users click on program name of a run to get the details, but it takes them to the program details page. Solution: remove the link from run pointing to the program, instead, put the link into the dropdown content or icon with a link or something
- if program install fails from git pull like no branch, show error
- git should not only clone but init submodules too
- provide default python version in config, not only default placeholder text
- make default file input option as not to be uploaded
- check for output files if exist after successful run
- check email notifs containing service name as username
- if branch or hash or tag has space, handle it in program install
- if program is deleted, delete the associated test run
- make it possible to stop program in queue
- add a switch to runs whether to a) copy over just the necessary inherited files b) all original files including git (this is the default now but a) should be the default)
- show successful test at the programs page
- add comment to installed program
- don't copy over inheritable files, rather, use the original one
- if a package is being installed with a name X, and another package named X is wanted to be installed again, it crashes
- Write the comment of a program, run and library into a file, and support markdown. Make it appendable.
- make property public for input and output files, and if a file is not public, ask for token
-->

<!-- 
- Test stopping feature, especially already stopped running and deleted running

 -->