# ================= IMPORTS =================
import os
import sqlite3
import time
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import Flask, render_template_string, request, redirect, session, send_from_directory
from flask_socketio import SocketIO, emit

# ================= CONFIG =================
DB = "chat.db"
UPLOAD_FOLDER = "uploads"

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_burmalda_777'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

socketio = SocketIO(app, cors_allowed_origins="*")

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    
# ================= NO CACHE =================
@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r

# ================= DB =================
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, message TEXT, timestamp REAL)")
    conn.commit()
    conn.close()

def save_message(username, message):
    with sqlite3.connect(DB) as conn:
        conn.execute("INSERT INTO messages (username, message, timestamp) VALUES (?, ?, ?)", (username, message, time.time()))

def load_messages():
    with sqlite3.connect(DB) as conn:
        return conn.execute("SELECT username, message FROM messages ORDER BY id ASC").fetchall()

# ================= AUTH =================
@app.route("/")
def home():
    if "user" in session:
        return redirect("/chat")
    return render_template_string(AUTH_HTML)

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")

    with sqlite3.connect(DB) as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE username=?", (username,)).fetchone()

    if row and check_password_hash(row[0], password):
        session["user"] = username
        session.permanent = True
        return redirect("/chat")

    return "Неверный логин или пароль. <a href='/'>Назад</a>"

@app.route("/register", methods=["POST"])
def register():
    username = request.form.get("username")
    password_raw = request.form.get("password")

    if not username or not password_raw:
        return "Заполни все поля!"

    password = generate_password_hash(password_raw)

    try:
        with sqlite3.connect(DB) as conn:
            conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password))
        return "Регистрация успешна! <a href='/'>Войти</a>"
    except sqlite3.IntegrityError:
        return "Этот ник уже занят! <a href='/'>Назад</a>"

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ================= UPLOAD =================
@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files or "user" not in session:
        return "error"

    file = request.files["file"]
    filename = str(int(time.time())) + "_" + secure_filename(file.filename)

    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    msg = f'<img src="/uploads/{filename}" style="max-width:250px; border-radius:10px;">'

    save_message(session["user"], msg)
    socketio.emit("message", {"user": session["user"], "text": msg})

    return "ok"

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ================= CHAT =================
@app.route("/chat")
def chat():
    if "user" not in session:
        return redirect("/")
    return render_template_string(CHAT_HTML, user=session["user"])

# ================= SOCKET =================
@socketio.on("connect")
def on_connect():
    emit("history", load_messages())

@socketio.on("message")
def handle_message(data):
    if "user" in session:
        save_message(session["user"], data["text"])
        socketio.emit("message", {"user": session["user"], "text": data["text"]})

# ================= HTML =================
AUTH_HTML = """
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { background:#0f0f0f; color:white; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh; margin:0; }
.box { width:85%; max-width:350px; background:#1e1e1e; padding:20px; border-radius:15px; }
input, button { width:100%; padding:12px; margin:8px 0; border:none; border-radius:8px; }
input { background:#2a2a2a; color:white; }
button { background:#4a90e2; color:white; }
</style></head>
<body><div class="box">
<h2>Burmalda</h2>
<form method="POST" action="/login">
<input name="username" placeholder="Логин" required>
<input name="password" type="password" placeholder="Пароль" required>
<button>Войти</button>
</form>
<form method="POST" action="/register">
<input name="username" placeholder="Ник" required>
<input name="password" type="password" placeholder="Пароль" required>
<button>Регистрация</button>
</form>
</div></body></html>
"""

CHAT_HTML = """
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { margin:0; background:#0f0f0f; color:white; font-family:sans-serif; display:flex; flex-direction:column; height:100vh; }
#chat { flex:1; overflow:auto; padding:10px; }
.msg { margin:5px; padding:10px; background:#1e1e1e; border-radius:10px; }
.me { background:#4a90e2; }
#ui { display:flex; padding:10px; gap:5px; }
input { flex:1; padding:10px; }
button { padding:10px; }
</style></head>
<body>
<div id="chat"></div>
<div id="ui">
<input id="m">
<button onclick="send()">Send</button>
</div>

<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
<script>
const socket = io({
    transports: ["websocket", "polling"],
    reconnection: true
});

const chat = document.getElementById("chat");
const myNick = "{{user}}";

function add(u, t){
    let d = document.createElement("div");
    d.className = "msg" + (u === myNick ? " me" : "");
    d.innerHTML = "<b>"+u+":</b><br>"+t;
    chat.appendChild(d);
    chat.scrollTop = chat.scrollHeight;
}

socket.on("history", data => {
    chat.innerHTML = "";
    data.forEach(m => add(m[0], m[1]));
});

socket.on("message", d => add(d.user, d.text));

function send(){
    let i = document.getElementById("m");
    if(i.value.trim()){
        socket.emit("message", {text:i.value});
        i.value="";
    }
}
</script>
</body></html>
"""

# ================= RUN =================
init_db()
