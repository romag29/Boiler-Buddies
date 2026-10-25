# BoilerBuddies

BoilerBuddies is a Flask + SQLite campus friendship and meetup app. This version replaces fictional seed profiles and in-memory demo interactions with persistent accounts, editable profiles, database-backed meetups, and real join/leave actions.

## Features

- Account registration/sign-in with password hashing
- Persistent student profiles and interests
- Discover other registered users with major, residence, and interest filters
- Create future-dated meetups at listed public campus locations
- Join/leave meetups; attendee counts persist
- Meetup hosts can delete their own meetups
- Optional Gemma AI via local Ollama, with useful fallback suggestions
- CSRF protection for state-changing form and API requests
- Responsive interface

## Run locally

Python 3.10+ recommended.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. The SQLite database is created automatically at `boilerbuddies.sqlite3` on first launch. Keep this file backed up if you want to preserve users and meetups.

## Optional AI

Install Ollama, then run:

```bash
ollama pull gemma3:4b
ollama serve
```

The default model endpoint is `http://localhost:11434/api/chat`. Change `GEMMA_MODEL` and `OLLAMA_URL` in your environment as needed. Without Ollama, AI endpoints return a built-in fallback; accounts, profiles, and meetups still work.

## Before deploying publicly

This is a functional starter app, **not yet a production-ready campus service**. Before public deployment:
- Set a strong persistent `SECRET_KEY` environment variable. Without it, sessions will be invalidated when the app restarts.
- Serve only behind HTTPS and set `COOKIE_SECURE=1`.
- Add Purdue email verification (currently any email format can register; no email is sent).
- Add account recovery, account deletion/export, reporting/blocking, moderation, rate limiting, logging/monitoring, database backups, and a privacy/security review.
- Consider PostgreSQL instead of SQLite for a multi-worker deployment.
- Add consent and clear privacy terms before students add real personal data.
- Avoid room numbers, live location, or exact residential details. Meetups should remain in public locations.

The app starts on `127.0.0.1` by default. Configure a suitable production WSGI server and hosting platform for deployment; do not use Flask's development server for production.

## Project layout

```text
boilerbuddies/
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── templates/
│   ├── auth.html
│   ├── index.html
│   ├── landing.html
│   └── profile.html
└── static/
    ├── app.js
    └── styles.css
```
