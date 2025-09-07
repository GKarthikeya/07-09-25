import os
import calendar
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session
from flask_session import Session
from attendance_scraper import login_and_get_attendance

app = Flask(__name__)

# --- Session config: store data temporarily on filesystem (/tmp) ---
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "/tmp/flask_session"
app.config["SESSION_PERMANENT"] = False
Session(app)


@app.route("/")
def home():
    return render_template("login.html")


@app.route("/attendance", methods=["POST"])
def attendance():
    username = request.form.get("username")
    password = request.form.get("password")

    if not username or not password:
        return render_template("login.html", error="Please enter username and password.")

    # --- Fetch attendance ---
    data = login_and_get_attendance(username, password)

    # --- Login failed? ---
    if not data.get("overall", {}).get("success"):
        return render_template(
            "login.html",
            error=data.get("overall", {}).get("message", "Login failed.")
        )

    # --- Store streak & daily data in session ---
    session["daily_data"] = data.get("daily", {})
    session["streak_data"] = data.get("streak", {})
    session["months"] = sorted({d[:7] for d in session["streak_data"].keys()})  # YYYY-MM
    session.modified = True

    # --- Subject table ---
    subjects = data.get("subjects", {})
    table_data = []
    for i, (code, sub) in enumerate(subjects.items(), start=1):
        table_data.append({
            "sno": i,
            "code": code,
            "name": sub["name"],
            "present": sub["present"],
            "absent": sub["absent"],
            "percentage": sub["percentage"],
            "status": sub["status"]
        })

    return render_template("attendance.html", table_data=table_data, overall=data["overall"])


@app.route("/streak")
def streak():
    streak_data = session.get("streak_data", {})
    daily_data = session.get("daily_data", {})
    if not streak_data:
        return redirect(url_for("home"))

    months = sorted({d[:7] for d in streak_data.keys()})
    selected_month = request.args.get("month", months[-1])
    year, month = map(int, selected_month.split("-"))

    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(year, month)

    return render_template(
        "streak.html",
        streak_data=streak_data,
        daily_data=daily_data,   # 👈 Added
        months=months,
        current_month=selected_month,
        month_days=month_days,
        year=year,
        month=month
    )



if __name__ == "__main__":
    # Local dev only; on Render we run via gunicorn from Dockerfile
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)), debug=True)

