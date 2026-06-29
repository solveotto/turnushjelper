from flask import Blueprint, render_template

legal = Blueprint("legal", __name__)


@legal.route("/personvern")
def personvern():
    """Public privacy policy page (personvernerklæring)."""
    return render_template("personvern.html", page_name="Personvern")
