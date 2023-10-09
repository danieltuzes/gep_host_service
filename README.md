# GEP host service

Execute data-orineted python scripts from a web interface. You can store different programs, and multiple execute runs, and all your inputs and outputs will be available for download via a web browser. No more python installation and manual config editing for program executors, saving developers from providing support.

## Requirements on the program

The programs must meet specific design requirements:

1. The program must be installable with a `pip install .` issued in the root, otherwise, the `requirements.txt` will be installed only.
2. The files and their paths are defined in a python ini file at `config/MasterConfig.cfg`, stored under the sections inputs and outputs.
3. Must be executable with a single command from `python -m`, e.g. `python -m my_module`.
4. Outputs must be saved within the root folder.

## Installing

Install the library from source code by issuing `pip install .` in the root. For development, install the requirements too.

## Startin the service

- For production, run `python -m gep_host`
- For debugging, run `python -m gep_host --debug`,
