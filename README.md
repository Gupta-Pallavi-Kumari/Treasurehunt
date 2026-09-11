# ADS Treasure Hunt

A lightweight Flask + SQLite treasure hunt for the Department of AI & Data Science college fest.

## Structure

```text
Treasure_Hunt/
├── app.py
├── database.db
├── generate_qr.py
├── import_team_logins.py
├── render.yaml
├── requirements.txt
├── templates/
│   ├── index.html
│   ├── hunt.html
│   ├── admin_login.html
│   └── admin.html
└── static/
    ├── style.css
    └── script.js
```

## Run locally

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Open `http://127.0.0.1:5000`.

The configured coordinator login is username `admin@123` and password `ecet@admin`. Keep these values in `.env`, not in frontend code.

## Admin setup

1. Run `python import_team_logins.py` once. It imports the 20 teams from `treasure_hunt_team_login_data.pdf`, hashes their passwords, and removes unlisted student accounts.
2. Open `/admin/login` and sign in with the coordinator credentials.
3. Configure the eight levels, QR tokens, clues, and hints.
4. Select **Download QR PDF** to generate printable QR codes. Each QR encodes its backend `/scan/<token>` URL.
5. Give each team the exact team name and password from the supplied PDF.

### Start and stop the game

1. Log in to `/admin/login`.
2. Press **Start game**. The server starts the official competition timer and student logins become available.
3. When the winner and runners-up are decided, press **Stop game**.
4. The timer freezes, all further QR scans are blocked, and students see **Game Over**.
5. The admin page shows the winner, runner-up, and third place from the teams that completed level 8, ordered by completion time.

### Reset for a new event

Press **Reset game** in the admin competition controls. This clears the global timer, stops the game, resets every team to level 1, removes violations, wrong attempts, start/completion timestamps, statuses, results, and activity logs. It keeps the authorized team accounts and configured QR tokens/hints.

### QR camera access

The scanner uses `html5-qrcode` for wider Android/iPhone browser support and keeps manual token entry as a fallback. Camera access requires `localhost` or HTTPS; it will not work when the site is opened from an insecure HTTP address on a phone. Allow the browser camera permission and use the phone's back camera.

The existing database is migrated on startup. Missing levels are added automatically, so the included starter database becomes an eight-level database without losing existing records. The admin dashboard intentionally does not allow arbitrary new student accounts.

## How validation works

A student login creates no client-owned state: the server stores the team, start time, current level, status, violation count, wrong attempts, and completion time. Every scan compares the submitted token with the active token for the team's current level in SQLite. A wrong level cannot advance the team, while a correct scan stores an activity event and advances exactly one level. Level 8 is the final round and marks the team completed with the congratulations message.

Tab visibility changes and window blur events are reported to the backend. The third recorded violation marks the team `ELIMINATED` and blocks scans. Browser detection is best-effort, so coordinators should still monitor the activity log.

## QR/PDF workflow

The supplied `treasure_hunt_qr_codes.pdf` contains the eight visible clue cards, not embedded QR image objects. Those exact clue texts are loaded into levels 1-8. Configure the matching QR tokens directly in **Level management**, then use **Download QR PDF** to generate QR codes. A correct backend QR scan reveals only the clue belonging to that scanned level; an incorrect scan reveals no clue.

For phone scanning over local Wi-Fi, update the base URL in `generate_qr.py` from `localhost` to the computer's LAN IP.

## Render deployment

Create a Render Web Service from this folder. `render.yaml` supplies the build and start commands:

```text
Build: pip install -r requirements.txt
Start: gunicorn app:app
```

Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` as Render environment variables. SQLite is suitable for a small event but Render's local filesystem can be ephemeral; attach persistent storage or export the database before restarting if competition records must survive redeploys.
