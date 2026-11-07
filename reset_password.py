
import os
import sqlite3
from getpass import getpass
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "smartpark.db")


def main():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    try:
        print("\n--- SmartPark Password Reset ---")
        account = input(
            "Enter the email OR phone number of the original account: "
        ).strip()

        user = con.execute(
            """
            SELECT id, name, email, phone
            FROM users
            WHERE lower(email) = lower(?) OR phone = ?
            """,
            (account, account),
        ).fetchone()

        if user is None:
            print("\nNo matching account found.")
            print("Check the email or phone number and try again.")
            return

        print("\nAccount found:")
        print("Name:", user["name"])
        print("Email:", user["email"])
        print("Phone:", user["phone"])

        confirm = input(
            "\nIs this the correct account? Type YES to continue: "
        ).strip()

        if confirm != "YES":
            print("Cancelled. No changes were made.")
            return

        password = getpass("Enter your new password (at least 8 characters): ")
        confirm_password = getpass("Enter the new password again: ")

        if len(password) < 8:
            print("Password must be at least 8 characters.")
            return

        if password != confirm_password:
            print("Passwords do not match.")
            return

        con.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), user["id"]),
        )
        con.commit()

        print("\nPassword updated successfully.")
        print("Your existing reservations have not been deleted.")

    finally:
        con.close()


if __name__ == "__main__":
    main()
