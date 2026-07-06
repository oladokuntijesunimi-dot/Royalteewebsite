"""
Royal Tee Stitches — Flask backend
-----------------------------------
• Serves the marketing site + order form
• Saves every submission (+ reference image) to a local SQLite database
• /admin  — password-protected dashboard to view all orders
• /admin/change-password — update the admin password
• No email sending required

Run locally:
    pip install -r requirements.txt
    cp .env.example .env      # fill in ADMIN_PASSWORD (and SECRET_KEY)
    python app.py
"""

import base64
import os
import sqlite3
import uuid
from datetime import datetime
from functools import wraps

from flask import (Flask, flash, g, redirect, render_template,
                   request, jsonify, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-in-production-please")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024   # 8 MB

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DATABASE = os.path.join(app.root_path, "orders.db")

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS orders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT    NOT NULL,
            full_name   TEXT    NOT NULL,
            phone       TEXT    NOT NULL,
            order_date  TEXT,
            notes       TEXT,
            image_path  TEXT,

            -- Blouse
            bl_back TEXT, bl_full_length TEXT, bl_bust TEXT, bl_chest TEXT,
            bl_round_waist TEXT, bl_waist_under_bust TEXT, bl_bust_point TEXT,
            bl_nn TEXT, bl_half_length TEXT, bl_sleeve_length TEXT, bl_round_sleeve TEXT,

            -- Skirt
            sk_length TEXT, sk_hip TEXT, sk_waist TEXT,

            -- Gown
            gw_bust TEXT, gw_under_bust TEXT, gw_waist TEXT, gw_hip TEXT,
            gw_back TEXT, gw_shoulder_to_bust_pt TEXT, gw_nn TEXT,
            gw_half_length TEXT, gw_round_waist TEXT, gw_length TEXT,
            gw_sleeve TEXT, gw_round_sleeve TEXT,

            -- Trouser
            tr_waist TEXT, tr_hip TEXT, tr_thigh TEXT, tr_knee TEXT,
            tr_length TEXT, tr_bottom TEXT, tr_tight TEXT,

            status TEXT DEFAULT 'new'
        );

        CREATE TABLE IF NOT EXISTS admin (
            id            INTEGER PRIMARY KEY,
            password_hash TEXT NOT NULL
        );
    """)
    # Seed admin password from env on first run
    existing = db.execute("SELECT id FROM admin").fetchone()
    if not existing:
        raw = os.getenv("ADMIN_PASSWORD", "admin123")
        db.execute("INSERT INTO admin (id, password_hash) VALUES (1, ?)",
                   (generate_password_hash(raw),))
    db.commit()

# Initialise DB on first request
with app.app_context():
    init_db()

# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------------------------------------------------------------------------
# Measurement field map  (form-name → db-column)
# ---------------------------------------------------------------------------
FIELD_MAP = {
    # Blouse
    "blouse_back": "bl_back", "blouse_full_length": "bl_full_length",
    "blouse_bust": "bl_bust", "blouse_chest": "bl_chest",
    "blouse_round_waist": "bl_round_waist", "blouse_waist_under_bust": "bl_waist_under_bust",
    "blouse_bust_point": "bl_bust_point", "blouse_nn": "bl_nn",
    "blouse_half_length": "bl_half_length", "blouse_sleeve_length": "bl_sleeve_length",
    "blouse_round_sleeve": "bl_round_sleeve",
    # Skirt
    "skirt_length": "sk_length", "skirt_hip": "sk_hip", "skirt_waist": "sk_waist",
    # Gown
    "gown_bust": "gw_bust", "gown_under_bust": "gw_under_bust",
    "gown_waist": "gw_waist", "gown_hip": "gw_hip", "gown_back": "gw_back",
    "gown_shoulder_to_bust_pt": "gw_shoulder_to_bust_pt", "gown_nn": "gw_nn",
    "gown_half_length": "gw_half_length", "gown_round_waist": "gw_round_waist",
    "gown_length": "gw_length", "gown_sleeve": "gw_sleeve",
    "gown_round_sleeve": "gw_round_sleeve",
    # Trouser
    "trouser_waist": "tr_waist", "trouser_hip": "tr_hip", "trouser_thigh": "tr_thigh",
    "trouser_knee": "tr_knee", "trouser_length": "tr_length",
    "trouser_bottom": "tr_bottom", "trouser_tight": "tr_tight",
}

MEASUREMENT_SECTIONS = {
    "Blouse": [
        ("bl_back","Back"),("bl_full_length","Full Length"),("bl_bust","Bust"),
        ("bl_chest","Chest"),("bl_round_waist","Round Waist"),
        ("bl_waist_under_bust","Waist Under Bust"),("bl_bust_point","Bust Point"),
        ("bl_nn","N–N (Nipple to Nipple)"),("bl_half_length","Half Length"),
        ("bl_sleeve_length","Sleeve Length"),("bl_round_sleeve","Round Sleeve"),
    ],
    "Skirt": [
        ("sk_length","Length"),("sk_hip","Hip"),("sk_waist","Waist"),
    ],
    "Gown": [
        ("gw_bust","Bust"),("gw_under_bust","Under-Bust"),("gw_waist","Waist"),
        ("gw_hip","Hip"),("gw_back","Back"),
        ("gw_shoulder_to_bust_pt","Shoulder to Bust Pt"),("gw_nn","Nipple to Nipple"),
        ("gw_half_length","Half Length"),("gw_round_waist","Round Waist"),
        ("gw_length","Gown Length"),("gw_sleeve","Sleeve"),("gw_round_sleeve","Round Sleeve"),
    ],
    "Trouser": [
        ("tr_waist","Waist"),("tr_hip","Hip"),("tr_thigh","Thigh (Lap)"),
        ("tr_knee","Knee"),("tr_length","Length"),("tr_bottom","Bottom"),("tr_tight","Tight"),
    ],
}

# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/order")
def order_page():
    return render_template("order.html")

@app.route("/submit-order", methods=["POST"])
def submit_order():
    fd = request.form
    full_name    = (fd.get("full_name") or "").strip()
    phone_number = (fd.get("phone_number") or "").strip()
    if not full_name or not phone_number:
        return jsonify({"status": "error", "message": "Full name and phone number are required."}), 400

    # Handle optional image upload
    saved_image_path = None
    file = request.files.get("reference_image")
    if file and file.filename:
        if not allowed_file(file.filename):
            return jsonify({"status": "error", "message": "Unsupported image type. Use PNG, JPG, GIF or WEBP."}), 400
        ext = file.filename.rsplit(".", 1)[1].lower()
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        saved_image_path = os.path.join(UPLOAD_FOLDER, secure_filename(unique_name))
        file.save(saved_image_path)

    # Build insert
    cols = ["created_at","full_name","phone","order_date","notes","image_path"]
    vals = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        full_name,
        phone_number,
        (fd.get("order_date") or "").strip() or None,
        (fd.get("notes") or "").strip() or None,
        saved_image_path,
    ]
    for form_key, db_col in FIELD_MAP.items():
        v = (fd.get(form_key) or "").strip() or None
        cols.append(db_col)
        vals.append(v)

    placeholders = ", ".join("?" * len(vals))
    col_str      = ", ".join(cols)
    db = get_db()
    db.execute(f"INSERT INTO orders ({col_str}) VALUES ({placeholders})", vals)
    db.commit()

    return jsonify({"status": "success", "message": "Order received! We will be in touch shortly."}), 200

# ---------------------------------------------------------------------------
# Admin — login / logout
# ---------------------------------------------------------------------------
@app.route("/admin", methods=["GET","POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))

    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        db = get_db()
        row = db.execute("SELECT password_hash FROM admin WHERE id=1").fetchone()
        if row and check_password_hash(row["password_hash"], password):
            session["admin_logged_in"] = True
            session.permanent = False
            return redirect(url_for("admin_dashboard"))
        error = "Incorrect password. Please try again."

    return render_template("admin_login.html", error=error)

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

# ---------------------------------------------------------------------------
# Admin — dashboard
# ---------------------------------------------------------------------------
@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    db   = get_db()
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()

    query  = "SELECT * FROM orders WHERE 1=1"
    params = []
    if search:
        query  += " AND (full_name LIKE ? OR phone LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    if status:
        query  += " AND status = ?"
        params.append(status)
    query += " ORDER BY id DESC"

    orders = db.execute(query, params).fetchall()
    total  = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    new_c  = db.execute("SELECT COUNT(*) FROM orders WHERE status='new'").fetchone()[0]
    return render_template("admin_dashboard.html",
                           orders=orders, total=total, new_count=new_c,
                           sections=MEASUREMENT_SECTIONS,
                           search=search, status_filter=status)

# ---------------------------------------------------------------------------
# Admin — view single order
# ---------------------------------------------------------------------------
@app.route("/admin/order/<int:order_id>")
@login_required
def admin_order_detail(order_id):
    db    = get_db()
    order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        flash("Order not found.", "error")
        return redirect(url_for("admin_dashboard"))

    # Build a browser-accessible URL for the reference image if one exists
    image_url = None
    if order["image_path"] and os.path.exists(order["image_path"]):
        # Serve from /static/uploads/<filename>
        image_url = "/static/uploads/" + os.path.basename(order["image_path"])

    return render_template("admin_order_detail.html",
                           order=order, sections=MEASUREMENT_SECTIONS,
                           image_url=image_url)

# ---------------------------------------------------------------------------
# Admin — update order status
# ---------------------------------------------------------------------------
@app.route("/admin/order/<int:order_id>/status", methods=["POST"])
@login_required
def admin_update_status(order_id):
    new_status = request.form.get("status", "new")
    db = get_db()
    db.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
    db.commit()
    flash(f"Order #{order_id} marked as '{new_status}'.", "success")
    return redirect(url_for("admin_order_detail", order_id=order_id))

# ---------------------------------------------------------------------------
# Admin — delete order
# ---------------------------------------------------------------------------
@app.route("/admin/order/<int:order_id>/delete", methods=["POST"])
@login_required
def admin_delete_order(order_id):
    db = get_db()
    row = db.execute("SELECT image_path FROM orders WHERE id=?", (order_id,)).fetchone()
    if row and row["image_path"] and os.path.exists(row["image_path"]):
        try:
            os.remove(row["image_path"])
        except OSError:
            pass
    db.execute("DELETE FROM orders WHERE id=?", (order_id,))
    db.commit()
    flash(f"Order #{order_id} deleted.", "success")
    return redirect(url_for("admin_dashboard"))

# ---------------------------------------------------------------------------
# Admin — change password
# ---------------------------------------------------------------------------
@app.route("/admin/change-password", methods=["GET","POST"])
@login_required
def admin_change_password():
    error = success = None
    if request.method == "POST":
        current  = request.form.get("current_password", "")
        new_pw   = request.form.get("new_password", "")
        confirm  = request.form.get("confirm_password", "")
        db = get_db()
        row = db.execute("SELECT password_hash FROM admin WHERE id=1").fetchone()
        if not check_password_hash(row["password_hash"], current):
            error = "Current password is incorrect."
        elif len(new_pw) < 6:
            error = "New password must be at least 6 characters."
        elif new_pw != confirm:
            error = "New passwords do not match."
        else:
            db.execute("UPDATE admin SET password_hash=? WHERE id=1",
                       (generate_password_hash(new_pw),))
            db.commit()
            success = "Password updated successfully."
    return render_template("admin_change_password.html", error=error, success=success)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
