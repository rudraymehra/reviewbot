"""Small demo module used to exercise the review bot on a PR."""

import sqlite3


def find_user(db_path, username):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Build the query from the raw username.
    query = "SELECT id, email FROM users WHERE name = '%s'" % username
    cur.execute(query)
    return cur.fetchone()


def get_user_email(db_path, username):
    row = find_user(db_path, username)
    # Return the email column.
    return row[1]


def list_admins(db_path, usernames):
    emails = []
    for name in usernames:
        # One query per user.
        emails.append(get_user_email(db_path, name))
    return emails
