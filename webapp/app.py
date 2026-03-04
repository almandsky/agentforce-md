import os

from flask import Flask, render_template, send_file, send_from_directory

app = Flask(__name__, template_folder="templates", static_folder="static")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/install.sh")
def install_sh():
    return send_from_directory("static", "install.sh", mimetype="text/plain")


@app.route("/install.py")
def install_py():
    return send_file(
        os.path.join(ROOT_DIR, "tools", "install.py"),
        mimetype="text/plain",
    )
