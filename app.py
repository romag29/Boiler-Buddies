import os
import json
import sqlite3
import secrets
import urllib.request
import urllib.error
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = os.getenv("DATABASE_PATH", str(BASE_DIR / "boilerbuddies.sqlite3"))
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma3:4b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)
INTERESTS = ["coding", "gaming", "basketball", "coffee", "board games", "music",
             "fitness", "reading", "movies", "volunteering", "cooking", "art",
             "hiking", "study groups", "photography", "dance"]
PUBLIC_PLACES = ["WALC public study area", "Purdue Memorial Union public lounge",
                 "Public campus dining area", "Stewart Center public lobby",
                 "Krach Leadership Center public area", "Other public campus location"]

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT NOT NULL UNIQUE COLLATE NOCASE,
      password_hash TEXT NOT NULL,
      name TEXT NOT NULL,
      major TEXT NOT NULL DEFAULT '',
      year TEXT NOT NULL DEFAULT '',
      residence TEXT NOT NULL DEFAULT '',
      bio TEXT NOT NULL DEFAULT '',
      vibe TEXT NOT NULL DEFAULT 'Low-key',
      interests TEXT NOT NULL DEFAULT '[]',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS meetups (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      title TEXT NOT NULL,
      category TEXT NOT NULL,
      place TEXT NOT NULL,
      starts_at TEXT NOT NULL,
      description TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS meetup_members (
      meetup_id INTEGER NOT NULL REFERENCES meetups(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(meetup_id, user_id)
    );
    CREATE INDEX IF NOT EXISTS idx_meetups_starts ON meetups(starts_at);
    """)
    db.commit()
    db.close()

@app.before_request
def csrf_guard():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        token = session.get("_csrf_token")
        supplied = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
        # JSON API callers must send the token obtained from /api/csrf.
        if not token or not supplied or not secrets.compare_digest(token, supplied):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Invalid or missing CSRF token. Refresh and try again."}), 400
            flash("Your session expired. Please try again.", "error")
            return redirect(request.referrer or url_for("index"))

@app.context_processor
def inject_globals():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return {"csrf_token": session["_csrf_token"], "current_user": current_user(), "interests_options": INTERESTS}

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return dict(row) if row else None

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            if request.path.startswith("/api/"):
                return jsonify({"error": "Sign in required."}), 401
            flash("Please sign in to do that.", "error")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def profile_json(row, include_email=False):
    result = dict(row)
    result["interests"] = json.loads(result.get("interests") or "[]")
    result.pop("password_hash", None)
    if not include_email:
        result.pop("email", None)
    return result

@app.get("/")
def index():
    if current_user():
        return render_template("index.html", page="discover")
    return render_template("landing.html")

@app.get("/register")
def register():
    return render_template("auth.html", mode="register")

@app.post("/register")
def register_post():
    name = request.form.get("name", "").strip()[:60]
    email = request.form.get("email", "").strip().lower()[:254]
    password = request.form.get("password", "")
    if not name or not email or "@" not in email or len(password) < 10:
        flash("Enter your name and a valid email. Passwords must be at least 10 characters.", "error")
        return render_template("auth.html", mode="register"), 400
    try:
        db = get_db()
        cur = db.execute(
            "INSERT INTO users(email,password_hash,name) VALUES(?,?,?)",
            (email, generate_password_hash(password), name))
        db.commit()
        session.clear()
        session["user_id"] = cur.lastrowid
        session["_csrf_token"] = secrets.token_urlsafe(32)
        flash("Welcome to BoilerBuddies! Finish your profile to help people find shared interests.", "success")
        return redirect(url_for("profile"))
    except sqlite3.IntegrityError:
        flash("An account with that email already exists.", "error")
        return render_template("auth.html", mode="register"), 409

@app.get("/login")
def login():
    return render_template("auth.html", mode="login")

@app.post("/login")
def login_post():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        flash("Email or password was incorrect.", "error")
        return render_template("auth.html", mode="login"), 401
    session.clear()
    session["user_id"] = row["id"]
    session["_csrf_token"] = secrets.token_urlsafe(32)
    return redirect(url_for("index"))

@app.post("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("index"))

@app.get("/profile")
@login_required
def profile():
    user = current_user()
    user["interests"] = json.loads(user.get("interests") or "[]")
    return render_template("profile.html", user=user, interests=INTERESTS)

@app.post("/profile")
@login_required
def profile_post():
    user = current_user()
    name = request.form.get("name", "").strip()[:60]
    major = request.form.get("major", "").strip()[:100]
    year = request.form.get("year", "").strip()[:30]
    residence = request.form.get("residence", "").strip()[:80]
    bio = request.form.get("bio", "").strip()[:400]
    vibe = request.form.get("vibe", "Low-key").strip()[:30]
    interests = [i for i in request.form.getlist("interests") if i in INTERESTS][:12]
    if not name:
        flash("Your display name is required.", "error")
        return redirect(url_for("profile"))
    get_db().execute("""UPDATE users SET name=?,major=?,year=?,residence=?,bio=?,vibe=?,interests=?
                        WHERE id=?""",
                     (name, major, year, residence, bio, vibe, json.dumps(interests), user["id"]))
    get_db().commit()
    flash("Profile saved.", "success")
    return redirect(url_for("index"))

@app.get("/api/csrf")
def csrf():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return jsonify({"csrf_token": session["_csrf_token"]})

@app.get("/api/profiles")
@login_required
def profiles():
    major = request.args.get("major", "").strip().lower()
    residence = request.args.get("residence", "").strip().lower()
    interest = request.args.get("interest", "").strip().lower()
    rows = get_db().execute("SELECT * FROM users WHERE id != ? ORDER BY name", (current_user()["id"],)).fetchall()
    result = []
    for row in rows:
        p = profile_json(row)
        if major and major not in p["major"].lower(): continue
        if residence and residence not in p["residence"].lower(): continue
        if interest and not any(interest in i.lower() for i in p["interests"]): continue
        result.append(p)
    return jsonify(result)

def meetup_dict(row, user_id):
    item = dict(row)
    item["attendees"] = get_db().execute(
        "SELECT COUNT(*) FROM meetup_members WHERE meetup_id=?", (item["id"],)).fetchone()[0]
    item["joined"] = bool(get_db().execute(
        "SELECT 1 FROM meetup_members WHERE meetup_id=? AND user_id=?",
        (item["id"], user_id)).fetchone())
    item["is_host"] = item["user_id"] == user_id
    item["host"] = item.pop("host_name")
    item.pop("user_id", None)
    return item

@app.get("/api/meetups")
@login_required
def meetups():
    rows = get_db().execute("""SELECT m.*,u.name AS host_name FROM meetups m
      JOIN users u ON u.id=m.user_id ORDER BY m.starts_at ASC""").fetchall()
    return jsonify([meetup_dict(r, current_user()["id"]) for r in rows])

@app.post("/api/meetups")
@login_required
def create_meetup():
    data = request.get_json(silent=True) if request.is_json else request.form
    data = data or {}
    title = str(data.get("title", "")).strip()[:100]
    category = str(data.get("category", "Social")).strip()[:40]
    place = str(data.get("place", "")).strip()[:100]
    starts_at = str(data.get("starts_at", "")).strip()[:30]
    description = str(data.get("description", "")).strip()[:500]
    if not title or not place or not starts_at or not description:
        return jsonify({"error": "Title, public location, date/time, and description are required."}), 400
    if place not in PUBLIC_PLACES:
        return jsonify({"error": "Choose a listed public campus location."}), 400
    try:
        parsed = datetime.fromisoformat(starts_at)
        if parsed <= datetime.now():
            return jsonify({"error": "Choose a future date and time."}), 400
        starts_at = parsed.isoformat(timespec="minutes")
    except ValueError:
        return jsonify({"error": "Date/time is invalid."}), 400
    db = get_db()
    cur = db.execute("INSERT INTO meetups(user_id,title,category,place,starts_at,description) VALUES(?,?,?,?,?,?)",
                     (current_user()["id"], title, category, place, starts_at, description))
    db.execute("INSERT INTO meetup_members(meetup_id,user_id) VALUES(?,?)", (cur.lastrowid, current_user()["id"]))
    db.commit()
    row = db.execute("""SELECT m.*,u.name AS host_name FROM meetups m JOIN users u ON u.id=m.user_id WHERE m.id=?""",
                     (cur.lastrowid,)).fetchone()
    return jsonify(meetup_dict(row, current_user()["id"])), 201

@app.post("/api/meetups/<int:meetup_id>/join")
@login_required
def toggle_meetup(meetup_id):
    db = get_db()
    meetup = db.execute("SELECT id FROM meetups WHERE id=?", (meetup_id,)).fetchone()
    if not meetup:
        return jsonify({"error": "Meetup not found."}), 404
    uid = current_user()["id"]
    existing = db.execute("SELECT 1 FROM meetup_members WHERE meetup_id=? AND user_id=?", (meetup_id, uid)).fetchone()
    if existing:
        db.execute("DELETE FROM meetup_members WHERE meetup_id=? AND user_id=?", (meetup_id, uid))
        joined = False
    else:
        db.execute("INSERT INTO meetup_members(meetup_id,user_id) VALUES(?,?)", (meetup_id, uid))
        joined = True
    db.commit()
    count = db.execute("SELECT COUNT(*) FROM meetup_members WHERE meetup_id=?", (meetup_id,)).fetchone()[0]
    return jsonify({"joined": joined, "attendees": count})

@app.delete("/api/meetups/<int:meetup_id>")
@login_required
def delete_meetup(meetup_id):
    db = get_db()
    cur = db.execute("DELETE FROM meetups WHERE id=? AND user_id=?", (meetup_id, current_user()["id"]))
    db.commit()
    if not cur.rowcount:
        return jsonify({"error": "Meetup not found or you are not the host."}), 404
    return jsonify({"deleted": True})

@app.post("/api/ai")
@login_required
def ai_helper():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "icebreakers")
    profile = data.get("profile", {})
    if not isinstance(profile, dict):
        return jsonify({"error": "Profile context must be an object."}), 400
    goal = str(data.get("goal") or "meet people with shared interests").strip()[:300]
    if mode == "match":
        prompt = ("You are Gemma for BoilerBuddies, a friendly campus community app. Using only these "
                  "user-provided public profile fields, explain possible shared interests and suggest one "
                  "low-pressure public meetup. Don't infer sensitive traits or promise compatibility. Under 100 words.\n"
                  + json.dumps(profile))
    else:
        prompt = ("Generate four short, respectful conversation starters for meeting a new student at a public campus meetup. "
                  "Avoid flirting, sensitive personal questions, pressure, and private contact/location requests. Number the list.\n"
                  f"Context: {goal}\nProfile: {json.dumps(profile)}")
    payload = json.dumps({"model": GEMMA_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            result = json.loads(response.read().decode())
        answer = result.get("message", {}).get("content", "").strip()
        if not answer: raise ValueError("Empty response")
        return jsonify({"text": answer, "source": "gemma"})
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        if mode == "match":
            interests = profile.get("interests", [])
            shared = ", ".join(str(x) for x in interests[:3]) or "campus activities"
            answer = f"You may have something in common through {shared}. Try a short study session or lunch in a public campus space. Shared interests are a conversation starter, not a compatibility guarantee."
        else:
            answer = "1. What class has been the most interesting this week?\n2. Have you found a favorite public study spot?\n3. What do you like doing on a free afternoon?\n4. Would you be interested in a small group lunch or study session?"
        return jsonify({"text": answer, "source": "fallback", "note": "Ollama is unavailable; install/start Ollama and pull the configured Gemma model for live AI."})

@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "Request too large."}), 413

init_db()

if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")), debug=False)
