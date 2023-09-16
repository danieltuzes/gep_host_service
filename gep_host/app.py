import logging
from .routes import app

if __name__ == "__main__":
    logging.info("Webservice started.")
    app.run(debug=True)
