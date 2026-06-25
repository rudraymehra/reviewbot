"""Demo payment service with intentionally planted issues (for reviewer demo)."""

import sqlite3


def get_user(db, user_id):
    # planted: SQL injection via string formatting
    cursor = db.cursor()
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    cursor.execute(query)
    return cursor.fetchone()


def total_spent(db, user_id):
    # planted: unhandled None — get_user can return None for an unknown id
    user = get_user(db, user_id)
    return user["balance"] * 1.0


def enrich_orders(db, orders):
    # planted: N+1 query — one DB round-trip per order inside the loop
    result = []
    for order in orders:
        cur = db.cursor()
        cur.execute("SELECT name FROM products WHERE id = ?", (order["product_id"],))
        product = cur.fetchone()
        result.append({"order": order, "product": product})
    return result


def ChargeCard(amount, token):
    # planted: function naming violates snake_case convention used elsewhere
    return {"charged": amount, "token": token}
