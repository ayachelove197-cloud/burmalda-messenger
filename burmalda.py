
import os
import sqlite3
import time

from flask import Flask, render_template_string, request, redirect, session, send_from_directory, abort
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# ---------- Railway-friendly paths ----------
# Railway filesystem может быть не предназначен для постоянной записи.
# /tmp обычно доступен для записи.
DATA_DIR = os.environ.get("DATA_DIR", "/tmp/burmalda")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "chat.db")
UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_UPLOAD_MB = 5


# ---------- App ----------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change_me_in_railway_vars")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")


# ---------- No-cache ----------
@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r


# ---------- DB helpers ----------
def db_conn():
    # check_same_thread=False полезно при eventlet/threads сценариях
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with db_conn() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        conn.commit()

init_db()

def save_message(username, message):
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO messages (username, message, timestamp) VALUES (?, ?, ?)",
            (username, message, time.time())
        )
        conn.commit()

def load_messages(limit=200):
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT username, message FROM messages ORDER BY id ASC LIMIT ?",
            (limit,)
        ).fetchall()
    return rows


# ---------- Auth ----------
@app.route("/")
def home():
    if "user" in session:
        return redirect("/chat")
    return render_template_string(AUTH_HTML)

@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    with db_conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username=?",
            (username,)
        ).fetchone()

    if row and check_password_hash(row[0], password):
        session["user"] = username
        session.permanent = True
        return redirect("/chat")

    return "Неверный логин или пароль. <a href='/'>Назад</a>", 401

@app.route("/register", methods=["POST"])
def register():
    username = (request.form.get("username") or "").strip()
    password_raw = request.form.get("password") or ""

    if not username or not password_raw:
        return "Заполни все поля! <a href='/'>Назад</a>",
