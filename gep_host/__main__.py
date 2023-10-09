import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
import argparse
import os
import json
import sys

from flask import Flask
from gevent.pywsgi import WSGIServer

from .routes import main_routes
from .utils.set_conf import set_conf


def parse_json(json_str):
    if isinstance(json_str, str) and json_str != "":
        return json.loads(json_str)
    return {}


if __name__ == "__main__":
    descr = ("GEP host service: "
             "host your data-oriented python programs from a webpage, "
             "execute it, store and download inputs and outputs")
    parser = argparse.ArgumentParser(description=descr)
    parser.add_argument('--debug', action='store_true',
                        help="Enable debug mode for flask")
    args = parser.parse_args()

    app = Flask(__name__)

    set_conf(app.config)

    @app.context_processor
    def inject_config():
        return dict(service_name=app.config["service_name"],
                    email_placeholder=app.config["email_placeholder"],
                    host_name=app.config["host_name"],
                    lib_def_path=app.config["lib_def_path"])

    app.register_blueprint(main_routes)
    app.jinja_env.filters['parse_json'] = parse_json

    # Setup logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    log_format = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')

    logf_name = os.path.join(app.config["ROOT"], 'logs', 'app.log')
    os.makedirs(os.path.dirname(logf_name), exist_ok=True)
    file_h = RotatingFileHandler(logf_name, maxBytes=10000, backupCount=1)
    strm_h = logging.StreamHandler()

    for handler in [file_h, strm_h]:
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        handler.setFormatter(log_format)

    if args.debug:
        logging.info("Webservice is starting in debug mode.")
        app.run(debug=True, port=app.config["port"])
        logging.critical("Webservice is shutting down.")
        sys.exit(1)

    logging.info("Webservice is starting in prod mode.")
    http_server = WSGIServer(listener=(app.config['host_to'],
                                       app.config["port"]),
                             application=app)
    print("Server running on "
          f"http://{app.config['host_to']}:{app.config['port']}")
    http_server.serve_forever()
