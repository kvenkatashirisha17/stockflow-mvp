# StockFlow MVP — Inventory Management SaaS

A small, runnable multi-tenant inventory app built with Python, Flask, and SQLite. Each signup creates an organization and a single owner account. Product reads/writes are scoped to the signed-in user's organization.

## Features
- Email/password signup and login; passwords are hashed.
- Organization created on signup.
- Product create, list, search, edit, and delete.
- Product fields: name, SKU, description, quantity, cost price, selling price, optional low-stock threshold.
- Dashboard product count, total units, and low-stock list.
- Organization settings: name and default low-stock threshold.
- Per-organization SKU uniqueness.
- Server-side ownership scoping for product edits/deletes.

## Requirements
- Python 3.10+
- pip

## Run locally

### Windows (PowerShell or CMD)
```bash
cd stockflow_mvp
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### macOS / Linux
```bash
cd stockflow_mvp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 in your browser and create an account.

The SQLite database (`stockflow.db`) is created automatically on first run. Keep it private and back it up if you use real data.

## Important before deployment
This is an MVP/demo starter, not a hardened production SaaS. Before public deployment:
1. Set a strong random `SECRET_KEY` environment variable.
2. Turn off Flask debug mode (it is off by default in this app).
3. Use HTTPS and secure cookie settings behind a correctly configured production server.
4. Add CSRF protection, rate limiting, email verification, password reset, and automated tests.
5. Use a managed production database and backups if needed.
6. Review security and privacy requirements for your deployment.

## Scope notes
- No password reset, email sending, billing, integrations, warehouses, purchase orders, or stock movement history.
- One owner account per organization is enforced by the schema.
- Timestamps are stored as UTC ISO strings.
- The product threshold can be left blank to use the organization's default.
