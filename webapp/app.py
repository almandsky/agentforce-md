import os

from flask import Flask, Response, render_template, request, send_file

app = Flask(__name__, template_folder="templates", static_folder="static")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _base_url() -> str:
    return request.host_url.rstrip("/")


@app.route("/")
def index():
    return render_template("index.html", base_url=_base_url())


@app.route("/install.sh")
def install_sh():
    content = render_template("install.sh", base_url=_base_url())
    return Response(content, mimetype="text/plain")


@app.route("/install.py")
def install_py():
    return send_file(
        os.path.join(ROOT_DIR, "tools", "install.py"),
        mimetype="text/plain",
    )
