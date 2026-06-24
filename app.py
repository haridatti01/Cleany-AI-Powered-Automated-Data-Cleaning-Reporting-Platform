"""
app.py
Cleany - Automated Data Cleaning & Reporting Platform
Main Flask application: routes, session handling, and orchestration
of the cleaning / profiling / AI / reporting pipeline.
"""
import os
import uuid
import logging
import traceback
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from flask import (Flask, render_template, request, redirect, url_for,
                    session, flash, jsonify, send_from_directory, abort)
from werkzeug.utils import secure_filename

from database.db import init_db, db_cursor
from utils.auth import (hash_password, verify_password, is_valid_email,
                         is_valid_password, login_required)
from utils import cleaning, profiling, charts, ai_engine, reports

# --------------------------------------------------------------------------
# App configuration
# --------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
ALLOWED_EXTENSIONS = {"csv", "xls", "xlsx"}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["UPLOAD_DIR"] = UPLOAD_DIR
app.config["REPORT_DIR"] = REPORT_DIR

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "database"), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(os.path.join(BASE_DIR, "cleany.log"))]
)
logger = logging.getLogger("cleany.app")

with app.app_context():
    init_db()


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_current_user():
    if "user_id" not in session:
        return None
    with db_cursor() as cur:
        cur.execute("SELECT id, username, email FROM users WHERE id = ?", (session["user_id"],))
        row = cur.fetchone()
        return dict(row) if row else None


@app.context_processor
def inject_user():
    return {"current_user": get_current_user()}


# --------------------------------------------------------------------------
# Error handlers
# --------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Page not found."), 404


@app.errorhandler(413)
def too_large(e):
    flash("File is too large. Maximum upload size is 50MB.", "danger")
    return redirect(url_for("dashboard"))


@app.errorhandler(500)
def server_error(e):
    logger.error(f"Internal server error: {e}\n{traceback.format_exc()}")
    return render_template("error.html", code=500, message="Something went wrong."), 500


# --------------------------------------------------------------------------
# Auth routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    if get_current_user():
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("All fields are required.", "danger")
        elif not is_valid_email(email):
            flash("Please enter a valid email address.", "danger")
        elif not is_valid_password(password):
            flash("Password must be at least 8 characters and include a letter and a number.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        else:
            try:
                with db_cursor(commit=True) as cur:
                    cur.execute(
                        "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                        (username, email, hash_password(password)),
                    )
                flash("Account created successfully. Please log in.", "success")
                return redirect(url_for("login"))
            except Exception as e:
                logger.warning(f"Registration failed: {e}")
                flash("Username or email already exists.", "danger")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        with db_cursor() as cur:
            cur.execute(
                "SELECT * FROM users WHERE username = ? OR email = ?",
                (identifier, identifier),
            )
            user = cur.fetchone()
        if user and verify_password(password, user["password_hash"]):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username/email or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# --------------------------------------------------------------------------
# Dashboard & file management
# --------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM uploaded_files WHERE user_id = ? ORDER BY uploaded_at DESC",
            (session["user_id"],),
        )
        files = [dict(row) for row in cur.fetchall()]
    return render_template("dashboard.html", files=files)


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    if "file" not in request.files:
        flash("No file selected.", "danger")
        return redirect(url_for("dashboard"))

    file = request.files["file"]
    if file.filename == "":
        flash("No file selected.", "danger")
        return redirect(url_for("dashboard"))

    if not allowed_file(file.filename):
        flash("Invalid file type. Only CSV and Excel files are allowed.", "danger")
        return redirect(url_for("dashboard"))

    original_name = secure_filename(file.filename)
    ext = original_name.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}_{original_name}"
    filepath = os.path.join(UPLOAD_DIR, stored_name)

    try:
        file.save(filepath)
        # Validate it actually parses
        df_check = cleaning.load_dataset(filepath)
        if df_check.empty:
            raise ValueError("Uploaded file contains no data.")

        with db_cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO uploaded_files
                   (user_id, original_filename, stored_filename, file_type, rows, columns)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session["user_id"], original_name, stored_name, ext,
                 df_check.shape[0], df_check.shape[1]),
            )
            file_id = cur.lastrowid

        flash("File uploaded successfully. Processing...", "success")
        return redirect(url_for("process_file", file_id=file_id))

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        flash(f"Failed to process file: {e}", "danger")
        return redirect(url_for("dashboard"))


def _get_file_or_404(file_id):
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM uploaded_files WHERE id = ? AND user_id = ?",
            (file_id, session["user_id"]),
        )
        row = cur.fetchone()
    if not row:
        abort(404)
    return dict(row)


def _run_pipeline(file_record):
    """Runs the full cleaning + profiling + AI pipeline for a stored file."""
    filepath = os.path.join(UPLOAD_DIR, file_record["stored_filename"])
    cleaned_df, cleaning_report = cleaning.clean_dataset(filepath)

    profile = profiling.profile_dataset(cleaned_df, duplicates_before=cleaning_report["duplicates_before"])
    understanding = profiling.understand_dataset(cleaned_df)
    quality = profiling.compute_quality_score(profile, cleaning_report["outliers_iqr"], len(cleaned_df))
    insights = ai_engine.generate_ai_insights(profile, understanding, quality, cleaning_report, cleaned_df)

    # Persist cleaned CSV for reuse
    cleaned_name = f"cleaned_{file_record['stored_filename'].rsplit('.', 1)[0]}.csv"
    cleaned_path = os.path.join(UPLOAD_DIR, cleaned_name)
    cleaned_df.to_csv(cleaned_path, index=False)

    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE uploaded_files SET cleaned_filename = ?, quality_score = ?, rows = ?, columns = ? WHERE id = ?",
            (cleaned_name, quality["score"], len(cleaned_df), cleaned_df.shape[1], file_record["id"]),
        )

    return {
        "cleaned_df": cleaned_df,
        "cleaning_report": cleaning_report,
        "profile": profile,
        "understanding": understanding,
        "quality": quality,
        "insights": insights,
    }


@app.route("/process/<int:file_id>")
@login_required
def process_file(file_id):
    file_record = _get_file_or_404(file_id)
    try:
        result = _run_pipeline(file_record)
    except Exception as e:
        logger.error(f"Pipeline failed for file {file_id}: {e}\n{traceback.format_exc()}")
        flash(f"Error processing dataset: {e}", "danger")
        return redirect(url_for("dashboard"))

    df = result["cleaned_df"]
    chart_data = {
        "histograms": charts.generate_histograms(df),
        "boxplots": charts.generate_boxplots(df),
        "heatmap": charts.generate_correlation_heatmap(df),
    }

    return render_template(
        "results.html",
        file=file_record,
        profile=result["profile"],
        understanding=result["understanding"],
        quality=result["quality"],
        cleaning_report=result["cleaning_report"],
        insights=result["insights"],
        charts=chart_data,
        preview=df.head(15).to_html(classes="table table-sm table-striped", index=False, border=0),
    )


@app.route("/chat/<int:file_id>", methods=["GET", "POST"])
@login_required
def chat(file_id):
    file_record = _get_file_or_404(file_id)
    cleaned_path = os.path.join(UPLOAD_DIR, file_record["cleaned_filename"] or "")

    if not file_record["cleaned_filename"] or not os.path.exists(cleaned_path):
        flash("Please process this dataset before chatting with it.", "warning")
        return redirect(url_for("process_file", file_id=file_id))

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if not question:
            return jsonify({"error": "Question cannot be empty."}), 400
        try:
            df = pd.read_csv(cleaned_path)
            answer = ai_engine.answer_dataset_question(df, question)
            with db_cursor(commit=True) as cur:
                cur.execute(
                    "INSERT INTO chat_history (file_id, user_id, question, answer) VALUES (?, ?, ?, ?)",
                    (file_id, session["user_id"], question, answer),
                )
            return jsonify({"answer": answer})
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return jsonify({"error": str(e)}), 500

    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM chat_history WHERE file_id = ? AND user_id = ? ORDER BY created_at ASC",
            (file_id, session["user_id"]),
        )
        history = [dict(row) for row in cur.fetchall()]

    return render_template("chat.html", file=file_record, history=history)


# --------------------------------------------------------------------------
# Report generation & downloads
# --------------------------------------------------------------------------
@app.route("/report/<int:file_id>/<report_type>")
@login_required
def generate_report(file_id, report_type):
    file_record = _get_file_or_404(file_id)
    cleaned_path = os.path.join(UPLOAD_DIR, file_record["cleaned_filename"] or "")

    if not file_record["cleaned_filename"] or not os.path.exists(cleaned_path):
        flash("Please process this dataset before generating reports.", "warning")
        return redirect(url_for("process_file", file_id=file_id))

    try:
        df = pd.read_csv(cleaned_path)
        profile = profiling.profile_dataset(df)
        understanding = profiling.understand_dataset(df)
        cleaning_report = {"duplicates_before": 0, "duplicates_removed": 0,
                            "outliers_iqr": cleaning.detect_outliers_iqr(df)}
        quality = profiling.compute_quality_score(profile, cleaning_report["outliers_iqr"], len(df))
        insights = ai_engine.generate_ai_insights(profile, understanding, quality, cleaning_report, df)

        base_name = file_record["original_filename"].rsplit(".", 1)[0]
        ts = datetime.now().strftime("%Y%m%d%H%M%S")

        if report_type == "pdf":
            out_name = f"{base_name}_report_{ts}.pdf"
            out_path = os.path.join(REPORT_DIR, out_name)
            reports.export_pdf_report(df, profile, understanding, quality, cleaning_report,
                                       insights, out_path, dataset_name=file_record["original_filename"])
        elif report_type == "excel":
            out_name = f"{base_name}_report_{ts}.xlsx"
            out_path = os.path.join(REPORT_DIR, out_name)
            reports.export_excel_report(df, profile, quality, insights, out_path)
        elif report_type == "csv":
            out_name = f"{base_name}_cleaned_{ts}.csv"
            out_path = os.path.join(REPORT_DIR, out_name)
            reports.export_cleaned_csv(df, out_path)
        else:
            abort(404)

        with db_cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO reports (file_id, user_id, report_type, report_path) VALUES (?, ?, ?, ?)",
                (file_id, session["user_id"], report_type, out_name),
            )

        return redirect(url_for("download_report", filename=out_name))

    except Exception as e:
        logger.error(f"Report generation failed: {e}\n{traceback.format_exc()}")
        flash(f"Failed to generate report: {e}", "danger")
        return redirect(url_for("process_file", file_id=file_id))


@app.route("/reports/download/<path:filename>")
@login_required
def download_report(filename):
    return send_from_directory(REPORT_DIR, filename, as_attachment=True)


@app.route("/delete/<int:file_id>", methods=["POST"])
@login_required
def delete_file(file_id):
    file_record = _get_file_or_404(file_id)
    for fname in [file_record["stored_filename"], file_record["cleaned_filename"]]:
        if fname:
            path = os.path.join(UPLOAD_DIR, fname)
            if os.path.exists(path):
                os.remove(path)
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM uploaded_files WHERE id = ?", (file_id,))
    flash("Dataset deleted.", "info")
    return redirect(url_for("dashboard"))


# --------------------------------------------------------------------------
# API health check
# --------------------------------------------------------------------------
@app.route("/api/health")
def health_check():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
