from flask import Blueprint, render_template

dashboard_bp = Blueprint("dashboard_bp", __name__)

@dashboard_bp.route("/dashboard")
def dashboard():
    return render_template("dashboard_page.html", current_tab="dashboard")
