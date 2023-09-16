
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
import os

from flask import Flask

from .utils import install_program, delete_program, delete_run, run_program

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

PROJ_ROOT = Path(os.path.dirname(__file__)).parent.parent
app.config['UPLOAD_FOLDER'] = os.path.join(PROJ_ROOT, 'programs')

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
