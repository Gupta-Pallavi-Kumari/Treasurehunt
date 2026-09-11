"""Import the authorized team credentials supplied in treasure_hunt_team_login_data.pdf."""

import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash

import app

AUTHORIZED_TEAMS = {
    "Finders": "26JD1A5405",
    "OG": "26JD1A5429",
    "Leo": "26JD1A5408",
    "Alpha": "25JD1A5411",
    "Beta": "25JD1A5465",
    "Sigma": "25JD1A5404",
    "Pokemon": "25JD1A5481",
    "TheChargers": "25JD1A54E3",
    "Hunters": "25JD1A54G9",
    "Aloha": "24JD1A4548",
    "Glitch": "24JD1A4509",
    "RebelRoots": "24JD1A4559",
    "HuntWarriors": "24JD1A4584",
    "Gayatri": "24JD1A45B8",
    "Hemanth": "24JD1A4567",
    "Hype3": "23JD1A4507",
    "Delulu": "23JD1A4521",
    "Mystery": "23JD1A4513",
    "TechTitans": "23JD1A45A7",
    "PowerHunter": "23JD1A4573",
}


def import_teams():
    connection = app.connect()
    existing_names = {row[0] for row in connection.execute("SELECT name FROM teams")}
    removed = existing_names - set(AUTHORIZED_TEAMS)
    for name in removed:
        team = connection.execute("SELECT team_id FROM teams WHERE name = ?", (name,)).fetchone()
        if team:
            connection.execute("DELETE FROM events WHERE team_id = ?", (team[0],))
        connection.execute("DELETE FROM teams WHERE name = ?", (name,))

    for name, password in AUTHORIZED_TEAMS.items():
        team = connection.execute("SELECT id FROM teams WHERE name = ?", (name,)).fetchone()
        password_hash = generate_password_hash(password)
        if team:
            connection.execute("UPDATE teams SET password_hash = ? WHERE name = ?", (password_hash, name))
        else:
            team_id = "TH-" + app.secrets.token_hex(4).upper()
            connection.execute(
                "INSERT INTO teams (team_id, name, password_hash, started_at, created_at) VALUES (?, ?, ?, '', ?)",
                (team_id, name, password_hash, app.now_text()),
            )
            app.log_event(connection, team_id, "TEAM_IMPORTED", "Imported from authorized PDF")
    connection.commit()
    connection.close()
    print(f"Imported {len(AUTHORIZED_TEAMS)} authorized teams; removed {len(removed)} unlisted teams.")


if __name__ == "__main__":
    import_teams()
