
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
from configparser import ConfigParser, ExtendedInterpolation
import os

from flask import Flask

from .utils import install_program, delete_program, delete_run, run_program

__version__ = "0.0.1"

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

PROJ_ROOT = Path(os.path.dirname(__file__)).parent.parent
app.config['UPLOAD_FOLDER'] = os.path.join(PROJ_ROOT, 'programs')

conf_path = os.path.join(PROJ_ROOT, "gep_host_service", "host.cfg")
prg_config = ConfigParser(interpolation=ExtendedInterpolation())
prg_config.read(conf_path)

app.config["port"] = int(prg_config.get("settings", "port"))


@app.context_processor
def inject_config():
    return dict(host_name=prg_config.get("settings", "name"))


# Setup logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
log_format = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')

logf_name = os.path.join(PROJ_ROOT, 'logs', 'app.log')
os.makedirs(os.path.dirname(logf_name), exist_ok=True)
file_h = RotatingFileHandler(logf_name, maxBytes=10000, backupCount=1)
strm_h = logging.StreamHandler()

for handler in [file_h, strm_h]:
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    handler.setFormatter(log_format)
