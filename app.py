import os
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

    # Get attendance using scraper
    data = login_and_get_attendance(username, password)

    # If login failed or scraper returned error
    if not data.get("overall", {}).get("success"):
        return render_template(
            "login.html",
            error=data.get("overall", {}).get("message", "Login failed.")
        )

    # Save daily data temporarily in server-side session
    session["daily_data"] = data.get("daily", {})
    session["months_present"] = sorted({d[:7] for d in session["daily_data"].keys()})  # YYYY-MM
    session.modified = True

    # Prepare subject data for table
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
    daily_data = session.get("daily_data", {})
    if not daily_data:
        return redirect(url_for("home"))
    # Pass an initial date (latest available) so calendar opens on a relevant month
    initial_date = sorted(daily_data.keys())[-1] if daily_data else None
    return render_template("streak.html", daily_data=daily_data, initial_date=initial_date)


if __name__ == "__main__":
    # Local dev only; on Render we run via gunicorn from Dockerfile
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)), debug=True)
