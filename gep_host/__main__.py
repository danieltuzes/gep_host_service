import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
import argparse
import os
import json
import sys
import mimetypes

from flask import Flask
from gevent.pywsgi import WSGIServer

from .routes import main_routes, setup_dynamic_routes
from .utils.set_conf_init import set_conf, load_pages
from . import __version__


def parse_json(json_str):
    if isinstance(json_str, str) and json_str != "":
        return json.loads(json_str)
    return {}


def format_file_size(size):
    # Define the thresholds for each unit
    KB = 1024
    MB = KB * 1024
    GB = MB * 1024

    # Determine the appropriate unit and format the size
    if size < KB:
        return f"{size}B"
    elif size < MB:
        return f"{size / KB:.0f}KB"
    elif size < GB:
        return f"{size / MB:.0f}MB"
    else:
        return f"{size / GB:.0f}GB"


def filename_to_html_id(filename):
    # Remove file extension
    name_without_ext = filename.rsplit('.', 1)[0]

    # Replace special characters with underscores and ensure it doesn't start with a number
    sanitized_id = ''.join(['_' + char if char.isdigit() and i == 0 else char if char.isascii()
                           and char.isalnum() else '_' for i, char in enumerate(name_without_ext)])

    return sanitized_id


def define_args():
    descr = ("GEP host service: "
             "host your data-oriented python programs from a webpage, "
             "execute it, store and download inputs and outputs")
    parser = argparse.ArgumentParser(description=descr)
    parser.add_argument('-v', '--version', action='version',
                        version='%(prog)s ' + __version__)
    parser.add_argument('--debug', action='store_true',
                        help="Enable debug mode for flask")
    parser.add_argument('--master_config', help=('Required: path to the master config file. '
                                                 'This file contains the paths for the service.'),
                        default="config/MasterConfig.cfg",
                        metavar="path/to/MasterConfig.cfg")
    return parser.parse_args()


def configure_app(app: Flask, args: argparse.Namespace):
    mimetypes.add_type('font/woff2', '.woff2')
    prg_conf_path = set_conf(app.config, args.master_config)
    load_pages(app.config, prg_conf_path)

    @app.context_processor
    def inject_config():
        return dict(service_name=app.config["service_name"],
                    email_placeholder=app.config["email_placeholder"],
                    email_pattern=app.config["email_pattern"],
                    host_name=app.config["host_name"],
                    lib_def_path=app.config["lib_def_path"],
                    git_example=app.config['git_example'],
                    git_branch=app.config['git_branch'],
                    stripe_color=app.config['stripe_color'])

    setup_dynamic_routes(app.config.get("static pages", {}))
    app.register_blueprint(main_routes)
    app.jinja_env.filters['parse_json'] = parse_json
    app.jinja_env.filters['filesize'] = format_file_size
    app.jinja_env.filters['filename_to_html_id'] = filename_to_html_id

    return app


if __name__ == "__main__":
    args = define_args()
    app = Flask(__name__)
    configure_app(app, args)

    # Setup logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    log_format = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')

    logf_name = os.path.join(app.config["ROOT"], 'logs', 'app.log')
    os.makedirs(os.path.dirname(logf_name), exist_ok=True)
    file_h = RotatingFileHandler(logf_name, maxBytes=1000000, backupCount=1)
    strm_h = logging.StreamHandler()

    for handler in [file_h, strm_h]:
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        handler.setFormatter(log_format)

    if args.debug:
        logging.info("Webservice is starting in debug mode.")
        app.run(debug=True,
                port=app.config["port"],
                host=app.config['host_to'])
        logging.critical("Webservice is shutting down.")
        sys.exit(1)

    logging.info("Webservice is starting in prod mode.")
    http_server = WSGIServer(listener=(app.config['host_to'],
                                       app.config["port"]),
                             application=app)
    print("Server running on "
          f"http://{app.config['host_to']}:{app.config['port']}")
    http_server.serve_forever()
