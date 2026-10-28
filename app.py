import os
import sqlite3
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("STOCKFLOW_DB", os.path.join(APP_DIR, "stockflow.db"))
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-before-deployment")
DEFAULT_LOW_STOCK = 5


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS organizations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        default_low_stock_threshold INTEGER NOT NULL DEFAULT 5,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organization_id INTEGER NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organization_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        sku TEXT NOT NULL COLLATE NOCASE,
        description TEXT NOT NULL DEFAULT '',
        quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
        cost_price REAL,
        selling_price REAL,
        low_stock_threshold INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(organization_id, sku),
        FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
    );
    """)
    db.commit()
    db.close()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_org():
    if "user_id" not in session:
        return {"current_org": None}
    db = get_db()
    org = db.execute(
        "SELECT name FROM organizations WHERE id = ?", (session.get("organization_id"),)
    ).fetchone()
    return {"current_org": org["name"] if org else None}


@app.route("/")
def index():
    return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        org_name = request.form.get("organization_name", "").strip()

        if not email or "@" not in email or "." not in email.split("@")[-1]:
            flash("Please enter a valid email address.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif not org_name:
            flash("Organization name is required.", "error")
        else:
            db = get_db()
            exists = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if exists:
                flash("An account with that email already exists. Please log in.", "error")
            else:
                now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                cur = db.execute(
                    "INSERT INTO organizations (name, default_low_stock_threshold, created_at) VALUES (?, ?, ?)",
                    (org_name, DEFAULT_LOW_STOCK, now)
                )
                org_id = cur.lastrowid
                cur = db.execute(
                    "INSERT INTO users (organization_id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    (org_id, email, generate_password_hash(password), now)
                )
                db.commit()
                session.clear()
                session["user_id"] = cur.lastrowid
                session["organization_id"] = org_id
                session["email"] = email
                flash("Welcome to StockFlow! Your workspace is ready.", "success")
                return redirect(url_for("dashboard"))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT id, organization_id, email, password_hash FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["organization_id"] = user["organization_id"]
            session["email"] = user["email"]
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


def org_id():
    return session["organization_id"]


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    products = db.execute(
        "SELECT * FROM products WHERE organization_id = ? ORDER BY name COLLATE NOCASE",
        (org_id(),)
    ).fetchall()
    total_products = len(products)
    total_units = sum(p["quantity"] for p in products)
    org = db.execute(
        "SELECT default_low_stock_threshold FROM organizations WHERE id = ?", (org_id(),)
    ).fetchone()
    default_threshold = org["default_low_stock_threshold"]
    low_stock = [
        p for p in products
        if p["quantity"] <= (p["low_stock_threshold"] if p["low_stock_threshold"] is not None else default_threshold)
    ]
    return render_template("dashboard.html", total_products=total_products,
                           total_units=total_units, low_stock=low_stock,
                           default_threshold=default_threshold)


@app.route("/products")
@login_required
def products():
    search = request.args.get("q", "").strip()
    db = get_db()
    if search:
        rows = db.execute("""
            SELECT * FROM products
            WHERE organization_id = ? AND (name LIKE ? OR sku LIKE ?)
            ORDER BY name COLLATE NOCASE
        """, (org_id(), f"%{search}%", f"%{search}%")).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM products WHERE organization_id = ? ORDER BY name COLLATE NOCASE",
            (org_id(),)
        ).fetchall()
    org = db.execute("SELECT default_low_stock_threshold FROM organizations WHERE id = ?", (org_id(),)).fetchone()
    threshold = org["default_low_stock_threshold"]
    return render_template("products.html", products=rows, search=search, default_threshold=threshold)


def parse_product_form():
    name = request.form.get("name", "").strip()
    sku = request.form.get("sku", "").strip()
    description = request.form.get("description", "").strip()
    try:
        quantity = int(request.form.get("quantity", "0"))
        if quantity < 0:
            raise ValueError
    except ValueError:
        raise ValueError("Quantity must be a whole number greater than or equal to zero.")

    def optional_price(field):
        raw = request.form.get(field, "").strip()
        if not raw:
            return None
        try:
            value = float(raw)
            if value < 0:
                raise ValueError
            return value
        except ValueError:
            raise ValueError(f"{field.replace('_', ' ').title()} must be a non-negative number.")

    raw_threshold = request.form.get("low_stock_threshold", "").strip()
    if raw_threshold:
        try:
            threshold = int(raw_threshold)
            if threshold < 0:
                raise ValueError
        except ValueError:
            raise ValueError("Low stock threshold must be a whole number greater than or equal to zero.")
    else:
        threshold = None
    if not name:
        raise ValueError("Product name is required.")
    if not sku:
        raise ValueError("SKU is required.")
    return name, sku, description, quantity, optional_price("cost_price"), optional_price("selling_price"), threshold


@app.route("/products/new", methods=["GET", "POST"])
@login_required
def create_product():
    if request.method == "POST":
        try:
            values = parse_product_form()
            now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            db = get_db()
            db.execute("""
                INSERT INTO products
                (organization_id, name, sku, description, quantity, cost_price, selling_price,
                 low_stock_threshold, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (org_id(), *values, now, now))
            db.commit()
            flash("Product created successfully.", "success")
            return redirect(url_for("products"))
        except ValueError as exc:
            flash(str(exc), "error")
        except sqlite3.IntegrityError:
            flash("That SKU already exists in your organization.", "error")
    return render_template("product_form.html", product=None, page_title="Add product")


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    db = get_db()
    product = db.execute(
        "SELECT * FROM products WHERE id = ? AND organization_id = ?", (product_id, org_id())
    ).fetchone()
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("products"))
    if request.method == "POST":
        try:
            values = parse_product_form()
            now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            db.execute("""
                UPDATE products SET name=?, sku=?, description=?, quantity=?, cost_price=?,
                    selling_price=?, low_stock_threshold=?, updated_at=?
                WHERE id=? AND organization_id=?
            """, (*values, now, product_id, org_id()))
            db.commit()
            flash("Product updated successfully.", "success")
            return redirect(url_for("products"))
        except ValueError as exc:
            flash(str(exc), "error")
        except sqlite3.IntegrityError:
            flash("That SKU already exists in your organization.", "error")
    return render_template("product_form.html", product=product, page_title="Edit product")


@app.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
def delete_product(product_id):
    db = get_db()
    db.execute("DELETE FROM products WHERE id = ? AND organization_id = ?", (product_id, org_id()))
    db.commit()
    flash("Product deleted.", "success")
    return redirect(url_for("products"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    db = get_db()
    org = db.execute("SELECT * FROM organizations WHERE id = ?", (org_id(),)).fetchone()
    if request.method == "POST":
        name = request.form.get("organization_name", "").strip()
        raw = request.form.get("default_low_stock_threshold", "").strip()
        try:
            threshold = int(raw)
            if threshold < 0:
                raise ValueError
            if not name:
                raise ValueError("Organization name is required.")
            db.execute(
                "UPDATE organizations SET name=?, default_low_stock_threshold=? WHERE id=?",
                (name, threshold, org_id())
            )
            db.commit()
            flash("Settings saved.", "success")
            return redirect(url_for("settings"))
        except ValueError as exc:
            flash(str(exc) if str(exc) else "Default threshold must be a non-negative whole number.", "error")
    return render_template("settings.html", org=org)


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    init_db()
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))
