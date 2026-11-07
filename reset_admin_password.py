
import os
import sqlite3
import getpass
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "smartpark.db")

email = "admin@smartpark.local"

password = getpass.getpass("Enter your new admin password: ")
confirm = getpass.getpass("Confirm your new admin password: ")

if len(password) < 8:
    raise SystemExit("Password must be at least 8 characters.")

if password != confirm:
    raise SystemExit("Passwords do not match. No changes made.")

conn = sqlite3.connect(DB_PATH)

try:
    admin = conn.execute(
        "SELECT id FROM users WHERE email = ? AND role = ?",
        (email, "admin")
    ).fetchone()

    if admin is None:
        raise SystemExit(
            "Admin account not found. No changes made."
        )

    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(password), admin[0])
    )
    conn.commit()

    print("Admin password reset successfully.")
    print("Your existing reservations and other users were not changed.")

finally:
    conn.close()
