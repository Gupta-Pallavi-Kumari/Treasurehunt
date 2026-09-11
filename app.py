import io
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
MAX_VIOLATIONS = 3
PDF_HINTS = {
    1: "Rows arranged with the precision of an ordered sequence, each occupant assigned an implicit index. Here, instruction is dispensed methodically, though connectivity often falters. Seek the chamber where attendance is recorded, yet signals frequently vanish.",
    2: "I have keys, but open no locks. I have windows, but let in no breeze. I have a mouse, but it has no whiskers. Here, thoughts become commands and commands become results. Find the place I describe.",
    3: "I need no ceiling, yet I belong to the campus. Lines may divide me, but walls do not. Sometimes I am crowded, sometimes almost empty. People come here not to sit, but to move.",
    4: "I hold what moves, where chariots of steel rest in silence, awaiting their masters' return.",
    5: "No syllabus can silence this internal alarm, no lecture hall can offer it calm. Follow the aroma that rebels against academia, where a five-minute recess dissolves into an hour's amnesia. Where does the campus surrender when the tummy files its complaint?",
    6: "Here, torque reigns supreme over syntax, and camaraderie is forged amid the scent of oxidized metal and lubricant. Seek the domain where engineers materialize what others merely simulate upon a screen.",
    7: "Where does the outside world end and the campus begin, where every journey into the world of academia starts, and where visitors first arrive before stepping through the threshold?",
    8: "You have reached the end, but the highest point is not your destination. Find what carries people upward, then forget about going up. Every step creates two worlds: one that people notice, and one that people rarely do. The answer is not on the path. It is in the space the path leaves behind. Search where the journey upward casts its shadow on the ground.",
}


def now_text():
    return datetime.now(timezone.utc).isoformat()


def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    connection = connect()
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS levels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level_number INTEGER NOT NULL UNIQUE,
            clue TEXT NOT NULL DEFAULT '',
            hint TEXT NOT NULL DEFAULT '',
            token TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1,
            is_final INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL DEFAULT '',
            current_level INTEGER NOT NULL DEFAULT 1,
            started_at TEXT,
            finished_at TEXT,
            violation_count INTEGER NOT NULL DEFAULT 0,
            wrong_attempts INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'NOT STARTED',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT,
            event_type TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            level INTEGER,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS game_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            status TEXT NOT NULL DEFAULT 'NOT_STARTED',
            started_at TEXT,
            stopped_at TEXT
        );
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(teams)")}
    if "password_hash" not in columns:
        connection.execute("ALTER TABLE teams ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''")
    if "violation_count" not in columns:
        connection.execute("ALTER TABLE teams ADD COLUMN violation_count INTEGER NOT NULL DEFAULT 0")
    if "created_at" not in columns:
        connection.execute("ALTER TABLE teams ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
    if "status" in columns:
        connection.execute("UPDATE teams SET status = 'PLAYING' WHERE status = 'Active'")
    level_columns = {row[1] for row in connection.execute("PRAGMA table_info(levels)")}
    if "active" not in level_columns:
        connection.execute("ALTER TABLE levels ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    event_columns = {row[1] for row in connection.execute("PRAGMA table_info(events)")}
    if "level" not in event_columns:
        connection.execute("ALTER TABLE events ADD COLUMN level INTEGER")
    existing_levels = {row[0] for row in connection.execute("SELECT level_number FROM levels")}
    for number in range(1, 9):
        if number not in existing_levels:
            connection.execute(
                "INSERT INTO levels (level_number, clue, hint, token, active, is_final) VALUES (?, ?, ?, ?, 1, ?)",
                (number, f"Find the QR code for level {number}.", f"Your next clue is waiting at location {number}.", f"ADS-HUNT-{number}-{secrets.token_urlsafe(10)}", int(number == 8)),
            )
    connection.execute("UPDATE levels SET is_final = CASE WHEN level_number = 8 THEN 1 ELSE 0 END")
    for number, hint in PDF_HINTS.items():
        connection.execute(
            "UPDATE levels SET hint = ? WHERE level_number = ? AND (hint = '' OR hint LIKE 'Your next clue is waiting%')",
            (hint, number),
        )
    connection.execute("INSERT OR IGNORE INTO game_state (id, status) VALUES (1, 'NOT_STARTED')")
    connection.commit()
    connection.close()


def log_event(connection, team_id, event_type, detail="", level=None):
    connection.execute(
        "INSERT INTO events (team_id, event_type, detail, level, created_at) VALUES (?, ?, ?, ?, ?)",
        (team_id, event_type, detail, level, now_text()),
    )


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


def get_team(connection):
    team_id = session.get("team_id")
    return connection.execute("SELECT * FROM teams WHERE team_id = ?", (team_id,)).fetchone() if team_id else None


def get_game(connection):
    return connection.execute("SELECT * FROM game_state WHERE id = 1").fetchone()


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/start")
def start_hunt():
    name = request.form.get("team_name", "").strip()
    password = request.form.get("team_password", "")
    connection = connect()
    game = get_game(connection)
    if not game or game["status"] != "RUNNING":
        connection.close()
        flash("The treasure hunt has not started yet. Please wait for the coordinator.")
        return redirect(url_for("index"))
    team = connection.execute("SELECT * FROM teams WHERE lower(name) = lower(?)", (name,)).fetchone()
    if not team or not team["password_hash"] or not check_password_hash(team["password_hash"], password):
        connection.close()
        flash("Invalid Team Name or Password. Please check your details or contact the coordinator.")
        return redirect(url_for("index"))
    if team["status"] == "COMPLETED":
        connection.close()
        flash("Your team has already completed the treasure hunt.")
        return redirect(url_for("index"))
    if team["status"] == "ELIMINATED":
        connection.close()
        flash("Your team has been eliminated. Please contact the coordinator.")
        return redirect(url_for("index"))
    started_at = team["started_at"] or now_text()
    connection.execute("UPDATE teams SET started_at = ?, status = 'PLAYING' WHERE id = ?", (started_at, team["id"]))
    log_event(connection, team["team_id"], "LOGIN", "Team logged in", team["current_level"])
    connection.commit()
    connection.close()
    session["team_id"] = team["team_id"]
    pending_scan = session.pop("pending_scan", "")
    return redirect(url_for("hunt", scan=pending_scan) if pending_scan else url_for("hunt"))


@app.get("/hunt")
def hunt():
    connection = connect()
    game = get_game(connection)
    team = get_team(connection)
    level = connection.execute("SELECT * FROM levels WHERE level_number = ?", (team["current_level"],)).fetchone() if team else None
    connection.close()
    if not team:
        session.pop("team_id", None)
        return redirect(url_for("index"))
    return render_template("hunt.html", team=team, level=level, game=game, max_violations=MAX_VIOLATIONS)


@app.get("/scan/<token>")
def scanned_qr(token):
    if not session.get("team_id"):
        session["pending_scan"] = token
        return redirect(url_for("index"))
    return redirect(url_for("hunt", scan=token))


@app.post("/api/scan")
def scan():
    team_id = session.get("team_id")
    token = request.form.get("token", "").strip()
    if "/scan/" in token:
        token = token.split("/scan/", 1)[1].split("?", 1)[0].split("#", 1)[0]
    if not team_id or not token:
        return jsonify(ok=False, message="Something went wrong. Please contact the coordinator."), 400
    connection = connect()
    game = get_game(connection)
    team = get_team(connection)
    level = connection.execute("SELECT * FROM levels WHERE level_number = ? AND active = 1", (team["current_level"],)).fetchone() if team else None
    scanned = connection.execute("SELECT * FROM levels WHERE token = ? AND active = 1", (token,)).fetchone()
    if not game or game["status"] != "RUNNING":
        connection.close()
        return jsonify(ok=False, game_over=True, message="Game Over. The coordinator has stopped the treasure hunt."), 403
    if not team or team["status"] == "ELIMINATED":
        connection.close()
        return jsonify(ok=False, message="Your team has been eliminated. Please contact the coordinator."), 403
    if team["status"] == "COMPLETED":
        connection.close()
        return jsonify(ok=False, message="Your team has already completed the treasure hunt."), 403
    if not level or not scanned or scanned["level_number"] != level["level_number"]:
        connection.execute("UPDATE teams SET wrong_attempts = wrong_attempts + 1 WHERE id = ?", (team["id"],))
        log_event(connection, team_id, "INCORRECT_QR", "Incorrect QR code", team["current_level"])
        connection.commit()
        connection.close()
        return jsonify(ok=False, message="Incorrect QR Code! Please try again."), 400
    current_level = level["level_number"]
    log_event(connection, team_id, "CORRECT_QR", f"Level {current_level} QR accepted", current_level)
    if current_level == 8:
        finished_at = now_text()
        connection.execute("UPDATE teams SET status = 'COMPLETED', finished_at = ? WHERE id = ?", (finished_at, team["id"]))
        log_event(connection, team_id, "COMPLETED", "Treasure hunt completed", current_level)
        connection.commit()
        connection.close()
        return jsonify(ok=True, completed=True, message="Congratulations! You have successfully completed the Treasure Hunt!")
    next_level = current_level + 1
    connection.execute("UPDATE teams SET current_level = ? WHERE id = ?", (next_level, team["id"]))
    next_data = connection.execute("SELECT level_number, clue, hint FROM levels WHERE level_number = ?", (next_level,)).fetchone()
    connection.commit()
    connection.close()
    return jsonify(ok=True, completed=False, level=dict(next_data), revealed_level=current_level, hint=level["hint"])


@app.post("/api/interruption")
def interruption():
    connection = connect()
    team = get_team(connection)
    if not team or team["status"] != "PLAYING":
        connection.close()
        return jsonify(ok=False), 403
    count = team["violation_count"] + 1
    status = "ELIMINATED" if count >= MAX_VIOLATIONS else "PLAYING"
    connection.execute("UPDATE teams SET violation_count = ?, status = ? WHERE id = ?", (count, status, team["id"]))
    log_event(connection, team["team_id"], "VIOLATION", f"Tab switch detected ({count}/{MAX_VIOLATIONS})", team["current_level"])
    if status == "ELIMINATED":
        log_event(connection, team["team_id"], "ELIMINATED", "Maximum tab-switch violations reached", team["current_level"])
    connection.commit()
    connection.close()
    return jsonify(ok=True, violations=count, status=status)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if secrets.compare_digest(request.form.get("username", ""), ADMIN_USERNAME) and secrets.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.")
    return render_template("admin_login.html")


@app.get("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin_dashboard():
    connection = connect()
    game = get_game(connection)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "game_action":
            game_action = request.form.get("game_action")
            if game_action == "start" and game["status"] != "RUNNING":
                connection.execute("UPDATE game_state SET status = 'RUNNING', started_at = ?, stopped_at = NULL WHERE id = 1", (now_text(),))
                log_event(connection, None, "GAME_STARTED", "Competition started by admin")
                flash("Game started. Students can now log in.")
            elif game_action == "stop" and game["status"] == "RUNNING":
                connection.execute("UPDATE game_state SET status = 'OVER', stopped_at = ? WHERE id = 1", (now_text(),))
                log_event(connection, None, "GAME_STOPPED", "Competition stopped by admin")
                flash("Game stopped. The results are now frozen.")
            elif game_action == "reset":
                connection.execute("UPDATE game_state SET status = 'NOT_STARTED', started_at = NULL, stopped_at = NULL WHERE id = 1")
                connection.execute("UPDATE teams SET current_level = 1, started_at = '', finished_at = NULL, violation_count = 0, wrong_attempts = 0, status = 'NOT STARTED'")
                connection.execute("DELETE FROM events")
                flash("Game reset. All teams, timers, violations, levels, and activity are fresh.")
            connection.commit()
            game = get_game(connection)
        elif action == "upload_pdf":
            uploaded = request.files.get("qr_pdf")
            if uploaded and uploaded.filename.lower().endswith(".pdf"):
                upload_dir = os.path.join(BASE_DIR, "uploads")
                os.makedirs(upload_dir, exist_ok=True)
                uploaded.save(os.path.join(upload_dir, secure_filename(uploaded.filename)))
                flash("PDF uploaded. Match its decoded tokens to levels below.")
            else:
                flash("Please choose a PDF file.")
        elif action == "save_level":
            level_id = request.form.get("level_id")
            values = (request.form.get("level_number", type=int), request.form.get("clue", "").strip(), request.form.get("hint", "").strip(), request.form.get("token", "").strip(), 1 if request.form.get("active") else 0)
            if level_id:
                connection.execute("UPDATE levels SET level_number = ?, clue = ?, hint = ?, token = ?, active = ? WHERE id = ?", (*values, level_id))
            flash("Level configuration saved.")
        elif action == "team_action":
            team_id = request.form.get("team_id")
            team_action = request.form.get("team_action")
            if team_action == "reset":
                connection.execute("UPDATE teams SET current_level = 1, started_at = '', finished_at = NULL, violation_count = 0, wrong_attempts = 0, status = 'NOT STARTED' WHERE team_id = ?", (team_id,))
                connection.execute("DELETE FROM events WHERE team_id = ?", (team_id,))
            elif team_action == "eliminate":
                connection.execute("UPDATE teams SET status = 'ELIMINATED' WHERE team_id = ?", (team_id,))
            elif team_action == "restore":
                connection.execute("UPDATE teams SET status = 'PLAYING' WHERE team_id = ? AND status = 'ELIMINATED'", (team_id,))
            log_event(connection, team_id, f"ADMIN_{team_action.upper()}", "Admin action")
        connection.commit()
    teams = connection.execute("SELECT * FROM teams ORDER BY COALESCE(started_at, created_at) DESC").fetchall()
    levels = connection.execute("SELECT * FROM levels ORDER BY level_number").fetchall()
    events = connection.execute("SELECT * FROM events ORDER BY created_at DESC LIMIT 100").fetchall()
    counts = {status: connection.execute("SELECT COUNT(*) FROM teams WHERE status = ?", (status,)).fetchone()[0] for status in ("PLAYING", "COMPLETED", "ELIMINATED", "NOT STARTED")}
    rankings = connection.execute("SELECT name, finished_at, current_level FROM teams WHERE status = 'COMPLETED' ORDER BY finished_at").fetchall()
    connection.close()
    return render_template("admin.html", teams=teams, levels=levels, events=events, counts=counts, game=game, rankings=rankings)


@app.get("/admin/qr.pdf")
@admin_required
def qr_pdf():
    try:
        import qrcode
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except ImportError:
        return "Install qrcode[pil] and reportlab first.", 500
    connection = connect()
    levels = connection.execute("SELECT * FROM levels WHERE active = 1 ORDER BY level_number").fetchall()
    connection.close()
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    width, height = A4
    for index, level in enumerate(levels):
        if index:
            pdf.showPage()
        image = qrcode.make(request.url_root.rstrip("/") + "/scan/" + level["token"])
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        pdf.setFont("Helvetica-Bold", 22)
        pdf.drawCentredString(width / 2, height - 80, f"TREASURE HUNT - LEVEL {level['level_number']}")
        pdf.drawImage(ImageReader(buffer), width / 2 - 130, height / 2 - 130, 260, 260)
        pdf.setFont("Helvetica", 11)
        pdf.drawCentredString(width / 2, height / 2 - 165, "Place this QR code at the matching hunt location")
    pdf.save()
    output.seek(0)
    return send_file(output, mimetype="application/pdf", as_attachment=True, download_name="treasure_hunt_qr_codes.pdf")


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "0") == "1")
