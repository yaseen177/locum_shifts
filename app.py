from flask import Flask, request, redirect, url_for, render_template, flash, send_from_directory
import os
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
import sqlite3

app = Flask(__name__)  # ✅ Ensure this is defined BEFORE using @app.route

UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)  # ✅ Ensure the uploads folder exists

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app = Flask(__name__)
app.secret_key = "your_secret_key"

from datetime import datetime

@app.template_filter("format_date")
def format_date(value):
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return value  # Return as-is if it cannot be parsed
    return value



# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Flask-Mail configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'vanity.eyewear.group@gmail.com'  # Replace with your Gmail address
app.config['MAIL_PASSWORD'] = 'erzb ptbn hwio fonu'    # Replace with the app password you generated
app.config['MAIL_DEFAULT_SENDER'] = 'vanity.eyewear.group@gmail.com'

mail = Mail(app)

# Serializer for secure tokens
serializer = URLSafeTimedSerializer(app.secret_key)

# Database connection
def get_db_connection():
    conn = sqlite3.connect('shifts.db', timeout=10)  # Increase timeout to allow waiting for the lock to release
    conn.row_factory = sqlite3.Row
    return conn


# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, email, password_hash):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.first_name = ""
        self.surname = ""
        self.phone_number = ""
        self.address_line1 = ""
        self.address_line2 = ""
        self.city = ""
        self.county = ""
        self.country = ""
        self.postcode = ""

    def set_profile(self, first_name, surname, phone_number, address_line1, address_line2, city, county, country, postcode):
        self.first_name = first_name or ""
        self.surname = surname or ""
        self.phone_number = phone_number or ""
        self.address_line1 = address_line1 or ""
        self.address_line2 = address_line2 or ""
        self.city = city or ""
        self.county = county or ""
        self.country = country or ""
        self.postcode = postcode or ""

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()

    if user:
        user_obj = User(
            id=user["id"],
            username=user["username"],
            email=user["email"],
            password_hash=user["password_hash"]
        )
        
        # Set extra profile details
        user_obj.set_profile(
            first_name=user["first_name"] if "first_name" in user.keys() else "",
            surname=user["surname"] if "surname" in user.keys() else "",
            phone_number=user["phone_number"] if "phone_number" in user.keys() else "",
            address_line1=user["address_line1"] if "address_line1" in user.keys() else "",
            address_line2=user["address_line2"] if "address_line2" in user.keys() else "",
            city=user["city"] if "city" in user.keys() else "",
            county=user["county"] if "county" in user.keys() else "",
            country=user["country"] if "country" in user.keys() else "",
            postcode=user["postcode"] if "postcode" in user.keys() else ""
        )

        return user_obj

    return None


# Create users and shifts tables if they don't exist
with get_db_connection() as conn:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            company TEXT NOT NULL,
            town TEXT NOT NULL,
            postcode TEXT NOT NULL,
            booking_source TEXT NOT NULL,
            rate REAL NOT NULL,
            user_id INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

# Routes
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from collections import defaultdict
import calendar

from datetime import datetime

@app.route('/')
@login_required
def index():
    date_filter = request.args.get("date_filter", "")
    sort = request.args.get("sort", "date_desc")
    company_filter = request.args.get("company", "")
    booking_source_filter = request.args.get("booking_source", "")
    status_filter = request.args.get("status_filter", "")

    conn = get_db_connection()
    query = "SELECT * FROM shifts WHERE user_id = ?"
    params = [current_user.id]

    # Apply filters dynamically
    if date_filter == "upcoming":
        query += " AND shift_date >= DATE('now')"
    elif date_filter == "past":
        query += " AND shift_date < DATE('now')"
    elif date_filter == "this_week":
        query += " AND shift_date BETWEEN DATE('now', 'weekday 0', '-6 days') AND DATE('now', 'weekday 0')"
    elif date_filter == "this_month":
        query += " AND strftime('%Y-%m', shift_date) = strftime('%Y-%m', DATE('now'))"

    if company_filter:
        if company_filter == "OTHER":
            query += " AND company NOT IN ('VISION EXPRESS', 'SPECSAVERS', 'SCRIVENS', 'ASDA')"
        else:
            query += " AND company = ?"
            params.append(company_filter)

    if booking_source_filter:
        if booking_source_filter == "OTHER":
            query += " AND booking_source NOT IN ('VISION EXPRESS', 'LOCATE A LOCUM', 'TEAM LOCUM', 'DIRECT')"
        else:
            query += " AND booking_source = ?"
            params.append(booking_source_filter)

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)

    # Apply sorting
    if sort == "date_asc":
        query += " ORDER BY shift_date ASC"
    elif sort == "date_desc":
        query += " ORDER BY shift_date DESC"
    elif sort == "rate_asc":
        query += " ORDER BY rate ASC"
    elif sort == "rate_desc":
        query += " ORDER BY rate DESC"

    shifts = conn.execute(query, params).fetchall()
    conn.close()

    return render_template(
        "index.html",
        shifts=shifts,
        date_filter=date_filter,
        sort=sort,
        company_filter=company_filter,
        booking_source_filter=booking_source_filter,
        status_filter=status_filter,
    )


from flask import jsonify
from collections import defaultdict
import calendar
from datetime import datetime, timedelta

@app.route('/get_monthly_earnings')
@login_required
def get_monthly_earnings():
    conn = get_db_connection()

    # Query earnings grouped by month and year
    monthly_earnings_query = """
        SELECT strftime('%Y-%m', shift_date) AS month, SUM(rate) 
        FROM shifts 
        WHERE user_id = ?
        GROUP BY month
        ORDER BY month
    """
    monthly_earnings_data = conn.execute(monthly_earnings_query, (current_user.id,)).fetchall()
    conn.close()

    # Store earnings in a dictionary
    earnings_by_month = {}
    for month, total in monthly_earnings_data:
        earnings_by_month[month] = round(total, 2)

    # Ensure only active months are included (months that actually have earnings)
    months_labels = []
    earnings_values = []

    for month_str, earnings in earnings_by_month.items():
        year, month = map(int, month_str.split("-"))
        month_label = f"{calendar.month_abbr[month]} {year}"  # Converts "2024-01" to "Jan 2024"
        months_labels.append(month_label)
        earnings_values.append(earnings)

    return jsonify({"months": months_labels, "earnings": earnings_values})

@app.route('/monthly_earnings')
@login_required
def monthly_earnings():
    return render_template("monthly_earnings.html")


@app.route('/add', methods=('GET', 'POST'))
@login_required
def add():
    if request.method == 'POST':
        shift_date = request.form['shift_date']
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        company = request.form['company']
        other_company = request.form.get('other_company', None)
        town = request.form['town']
        postcode = request.form['postcode']
        booking_source = request.form['booking_source']
        other_booking_source = request.form.get('other_booking_source', None)
        rate = float(request.form['rate'])

        if company == "OTHER" and other_company:
            company = other_company
        if booking_source == "OTHER" and other_booking_source:
            booking_source = other_booking_source

        try:
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO shifts (shift_date, start_time, end_time, company, town, postcode, booking_source, rate, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (shift_date, start_time, end_time, company, town, postcode, booking_source, rate, current_user.id))
            conn.commit()
        except sqlite3.OperationalError as e:
            print("Database is locked error:", e)  # Debugging log
            flash("Database error, please try again later.", "danger")
        finally:
            conn.close()  # Ensure the connection is closed

        return redirect(url_for('index'))

    return render_template('add.html')

@app.route('/shift/<int:shift_id>')
@login_required
def view_shift(shift_id):
    conn = get_db_connection()
    shift = conn.execute(
        "SELECT * FROM shifts WHERE id = ? AND user_id = ?",
        (shift_id, current_user.id)
    ).fetchone()
    conn.close()

    if not shift:
        flash("Shift not found!", "danger")
        return redirect(url_for("index"))

    from datetime import datetime, timedelta

    # Ensure correct time format (HH:mm) before sending to template
    def format_time(time_str):
        if time_str:
            try:
                return datetime.strptime(time_str, "%H:%M:%S").strftime("%H:%M")
            except ValueError:
                return time_str  # If already correct format
        return ""

    shift_data = dict(shift)
    shift_data["start_time"] = format_time(shift_data["start_time"])
    shift_data["end_time"] = format_time(shift_data["end_time"])

    # Calculate hourly rate
    try:
        start_time_obj = datetime.strptime(shift_data["start_time"], "%H:%M")
        end_time_obj = datetime.strptime(shift_data["end_time"], "%H:%M")
        hours_worked = (end_time_obj - start_time_obj).seconds / 3600  # Convert seconds to hours
        hourly_rate = round(float(shift_data["rate"]) / hours_worked, 2) if hours_worked > 0 else "N/A"
    except:
        hourly_rate = "N/A"

    return render_template(
        "shift_detail.html",
        shift=shift_data,
        hourly_rate=hourly_rate
    )

@app.route('/shift/<int:shift_id>/update', methods=['POST'])
@login_required
def update_shift(shift_id):
    conn = get_db_connection()
    shift = conn.execute("SELECT * FROM shifts WHERE id = ? AND user_id = ?", (shift_id, current_user.id)).fetchone()

    # Handle case where shift is not found
    if shift is None:
        flash("Error: Shift not found!", "danger")
        conn.close()
        return redirect(url_for("index"))


    if not shift:
        flash("Shift not found!", "danger")
        return redirect(url_for("index"))

    # Get form data
    shift_date = request.form.get("shift_date")
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")
    company = request.form.get("company")
    town = request.form.get("town")
    postcode = request.form.get("postcode")
    booking_source = request.form.get("booking_source")
    rate = float(request.form.get("rate", 0))
    status = request.form.get("status")

    # Handle invoice upload
    invoice = shift["invoice"] if "invoice" in shift.keys() else None
    if "invoice" in request.files:
        invoice_file = request.files["invoice"]
        if invoice_file.filename:
            invoice_filename = f"invoice_{shift_id}.pdf"
            invoice_path = os.path.join("uploads", invoice_filename)
            invoice_file.save(invoice_path)
            invoice = invoice_filename  # Store file name in DB


import os
from flask import send_from_directory

UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/shift/<int:shift_id>/upload_invoice', methods=['POST'])
@login_required
def upload_invoice(shift_id):
    conn = get_db_connection()
    shift = conn.execute("SELECT * FROM shifts WHERE id = ? AND user_id = ?", (shift_id, current_user.id)).fetchone()

    if not shift:
        flash("Shift not found!", "danger")
        conn.close()
        return redirect(url_for("index"))

    if "invoice" in request.files:
        invoice_file = request.files["invoice"]
        if invoice_file.filename:
            invoice_filename = f"invoice_{shift_id}.pdf"
            invoice_path = os.path.join(app.config['UPLOAD_FOLDER'], invoice_filename)
            invoice_file.save(invoice_path)
            
            conn.execute("UPDATE shifts SET invoice = ? WHERE id = ? AND user_id = ?", (invoice_filename, shift_id, current_user.id))
            conn.commit()

    conn.close()
    flash("Invoice uploaded successfully!", "success")
    return redirect(url_for("view_shift", shift_id=shift_id))

import os

@app.route('/shift/<int:shift_id>/remove_invoice', methods=['POST'])
@login_required
def remove_invoice(shift_id):
    conn = get_db_connection()
    shift = conn.execute("SELECT * FROM shifts WHERE id = ? AND user_id = ?", (shift_id, current_user.id)).fetchone()

    if not shift:
        flash("Shift not found!", "danger")
        conn.close()
        return redirect(url_for("index"))

    # Get invoice filename
    invoice_filename = shift["invoice"]
    if invoice_filename:
        invoice_path = os.path.join(app.config['UPLOAD_FOLDER'], invoice_filename)
        
        # Remove file from server
        if os.path.exists(invoice_path):
            os.remove(invoice_path)

        # Remove invoice entry from the database
        conn.execute("UPDATE shifts SET invoice = NULL WHERE id = ? AND user_id = ?", (shift_id, current_user.id))
        conn.commit()

    conn.close()
    flash("Invoice removed successfully!", "success")
    return redirect(url_for("view_shift", shift_id=shift_id))



@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)



    # Update shift in database
    conn.execute(
        """
        UPDATE shifts 
        SET shift_date = ?, start_time = ?, end_time = ?, company = ?, town = ?, postcode = ?, 
            booking_source = ?, rate = ?, status = ?, invoice = ?
        WHERE id = ? AND user_id = ?
        """,
        (shift_date, start_time, end_time, company, town, postcode, booking_source, rate, status, invoice, shift_id, current_user.id),
    )
    conn.commit()
    conn.close()

    flash("Shift updated successfully!", "success")
    return redirect(url_for("view_shift", shift_id=shift_id))



@app.route('/edit/<int:id>', methods=('GET', 'POST'))
@login_required
def edit(id):
    conn = get_db_connection()
    shift = conn.execute('SELECT * FROM shifts WHERE id = ? AND user_id = ?', (id, current_user.id)).fetchone()

    if shift is None:
        flash('You are not authorized to edit this shift.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        shift_date = request.form['shift_date']
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        company = request.form['company']
        other_company = request.form.get('other_company', None)
        town = request.form['town']
        postcode = request.form['postcode']
        booking_source = request.form['booking_source']
        other_booking_source = request.form.get('other_booking_source', None)
        rate = float(request.form['rate'])

        if company == "OTHER" and other_company:
            company = other_company
        if booking_source == "OTHER" and other_booking_source:
            booking_source = other_booking_source

        conn.execute('''
            UPDATE shifts
            SET shift_date = ?, start_time = ?, end_time = ?, company = ?, town = ?, postcode = ?, booking_source = ?, rate = ?
            WHERE id = ? AND user_id = ?
        ''', (shift_date, start_time, end_time, company, town, postcode, booking_source, rate, id, current_user.id))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))

    conn.close()
    return render_template('edit.html', shift=shift)

@app.route('/delete/<int:shift_id>', methods=["POST"])
@login_required
def delete_shift(shift_id):
    conn = get_db_connection()
    conn.execute("UPDATE shifts SET deleted = 1 WHERE id = ? AND user_id = ?", (shift_id, current_user.id))
    conn.commit()
    conn.close()
    flash("Shift deleted. You can restore it from the Deleted Shifts page.", "warning")
    return redirect(url_for("index"))

# New route: Page showing deleted shifts
@app.route('/deleted_shifts')
@login_required
def deleted_shifts():
    conn = get_db_connection()
    shifts = conn.execute("SELECT * FROM shifts WHERE user_id = ? AND deleted = 1", (current_user.id,)).fetchall()
    conn.close()
    return render_template("deleted_shifts.html", shifts=shifts)

# New route: Restore a deleted shift
@app.route('/shift/<int:shift_id>/restore', methods=["POST"])
@login_required
def restore_shift(shift_id):
    conn = get_db_connection()
    conn.execute("UPDATE shifts SET deleted = 0 WHERE id = ? AND user_id = ?", (shift_id, current_user.id))
    conn.commit()
    conn.close()
    flash("Shift restored successfully!", "success")
    return redirect(url_for("deleted_shifts"))

# New route: Permanently delete a shift
@app.route('/shift/<int:shift_id>/permanent_delete', methods=["POST"])
@login_required
def permanent_delete_shift(shift_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM shifts WHERE id = ? AND user_id = ?", (shift_id, current_user.id))
    conn.commit()
    conn.close()
    flash("Shift permanently deleted!", "success")
    return redirect(url_for("deleted_shifts"))


@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            user_obj = User(id=user['id'], username=user['username'], email=user['email'], password_hash=user['password_hash'])
            login_user(user_obj)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    # Clear any existing flash messages from the session
    session.pop('_flashes', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


@app.route('/register', methods=('GET', 'POST'))
def register():
    if request.method == 'POST':
        first_name = request.form['first_name']
        surname = request.form['surname']
        username = request.form['username']
        email = request.form['email']
        phone_number = request.form['country_code'] + " " + request.form['phone_number']
        address_line1 = request.form['address_line1']
        address_line2 = request.form.get('address_line2', '')
        city = request.form['city']
        county = request.form.get('county', '')
        country = request.form['country']
        postcode = request.form['postcode']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        
        try:
            conn.execute("""
                INSERT INTO users 
                (first_name, surname, username, email, phone_number, address_line1, address_line2, city, county, country, postcode, password_hash) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (first_name, surname, username, email, phone_number, address_line1, address_line2, city, county, country, postcode, hashed_password))
            conn.commit()
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists.', 'danger')
        except sqlite3.OperationalError as e:
            flash(f'Database error: {e}', 'danger')
        finally:
            conn.close()  # Ensures connection closes, preventing database locks

    return render_template('register.html')

@app.route('/profile', methods=('GET', 'POST'))
@login_required
def profile():
    if request.method == 'POST':
        first_name = request.form['first_name']
        surname = request.form['surname']
        email = request.form['email']
        phone_number = request.form['phone_number']
        address_line1 = request.form['address_line1']
        address_line2 = request.form.get('address_line2', '')
        city = request.form['city']
        county = request.form.get('county', '')
        country = request.form['country']
        postcode = request.form['postcode']

        conn = get_db_connection()
        try:
            # Update user information in the database
            conn.execute("""
                UPDATE users 
                SET first_name = ?, surname = ?, email = ?, phone_number = ?, 
                    address_line1 = ?, address_line2 = ?, city = ?, county = ?, country = ?, postcode = ?
                WHERE id = ?
            """, (first_name, surname, email, phone_number, address_line1, address_line2, city, county, country, postcode, current_user.id))
            conn.commit()
            
            # Refresh current_user session data
            user = conn.execute("SELECT * FROM users WHERE id = ?", (current_user.id,)).fetchone()
            if user:
                current_user.first_name = user['first_name']
                current_user.surname = user['surname']
                current_user.email = user['email']
                current_user.phone_number = user['phone_number']
                current_user.address_line1 = user['address_line1']
                current_user.address_line2 = user['address_line2']
                current_user.city = user['city']
                current_user.county = user['county']
                current_user.country = user['country']
                current_user.postcode = user['postcode']
            
            flash('Profile updated successfully!', 'success')
        except sqlite3.OperationalError as e:
            flash(f'Database error: {e}', 'danger')
        finally:
            conn.close()

        return redirect(url_for('index'))  # Redirect to home page after updating

    return render_template('profile.html')

    if request.method == 'POST':
        first_name = request.form['first_name']
        surname = request.form['surname']
        email = request.form['email']
        phone_number = request.form['phone_number']
        address_line1 = request.form['address_line1']
        address_line2 = request.form.get('address_line2', '')
        city = request.form['city']
        county = request.form.get('county', '')
        country = request.form['country']
        postcode = request.form['postcode']

        conn = get_db_connection()
        try:
            conn.execute("""
                UPDATE users 
                SET first_name = ?, surname = ?, email = ?, phone_number = ?, 
                    address_line1 = ?, address_line2 = ?, city = ?, county = ?, country = ?, postcode = ?
                WHERE id = ?
            """, (first_name, surname, email, phone_number, address_line1, address_line2, city, county, country, postcode, current_user.id))
            conn.commit()
            flash('Profile updated successfully!', 'success')
        except sqlite3.OperationalError as e:
            flash(f'Database error: {e}', 'danger')
        finally:
            conn.close()

        return redirect(url_for('profile'))

    return render_template('profile.html')

    if request.method == 'POST':
        first_name = request.form['first_name']
        surname = request.form['surname']
        email = request.form['email']
        phone_number = request.form['phone_number']
        address_line1 = request.form['address_line1']
        address_line2 = request.form.get('address_line2', '')
        city = request.form['city']
        county = request.form.get('county', '')
        country = request.form['country']
        postcode = request.form['postcode']

        conn = get_db_connection()
        try:
            conn.execute("""
                UPDATE users 
                SET first_name = ?, surname = ?, email = ?, phone_number = ?, 
                    address_line1 = ?, address_line2 = ?, city = ?, county = ?, country = ?, postcode = ?
                WHERE id = ?
            """, (first_name, surname, email, phone_number, address_line1, address_line2, city, county, country, postcode, current_user.id))
            conn.commit()
            flash('Profile updated successfully!', 'success')
        except sqlite3.OperationalError as e:
            flash(f'Database error: {e}', 'danger')
        finally:
            conn.close()

        return redirect(url_for('profile'))

    return render_template('profile.html')


@app.route('/reset_password', methods=('GET', 'POST'))
def reset_password():
    if request.method == 'POST':
        email = request.form['email']

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user:
            token = serializer.dumps(email, salt='password-reset-salt')
            reset_url = url_for('reset_password_token', token=token, _external=True)
            msg = Message('Password Reset Request', recipients=[email])
            msg.body = f"Hi,\n\nClick the link below to reset your password:\n{reset_url}\n\nIf you didn't request this, please ignore the email."
            mail.send(msg)
            flash('A password reset link has been sent to your email.', 'info')
        else:
            flash('No account found with that email.', 'danger')

    return render_template('reset_password.html')

@app.route('/reset_password/<token>', methods=('GET', 'POST'))
def reset_password_token(token):
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except Exception as e:
        flash('The password reset link is invalid or has expired.', 'danger')
        return redirect(url_for('reset_password'))

    if request.method == 'POST':
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        conn.execute("UPDATE users SET password_hash = ? WHERE email = ?", (hashed_password, email))
        conn.commit()
        conn.close()

        flash('Your password has been reset. You can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password_token.html')

import os
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"xlsx"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Function to check allowed file types
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# Route: Upload Excel File
@app.route("/import_shifts", methods=["GET", "POST"])
@login_required
def import_shifts():
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file part", "danger")
            return redirect(request.url)

        file = request.files["file"]

        if file.filename == "":
            flash("No selected file", "danger")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(file_path)

            # Read Excel file to get column names
            df = pd.read_excel(file_path, engine="openpyxl")
            session["uploaded_file"] = file_path
            session["columns"] = df.columns.tolist()

            return redirect(url_for("map_columns"))

    return render_template("import_shifts.html")

# Route: Map Excel Columns to Website Fields
@app.route("/map_columns", methods=["GET", "POST"])
@login_required
def map_columns():
    if "uploaded_file" not in session:
        flash("No file uploaded", "danger")
        return redirect(url_for("import_shifts"))

    columns = session.get("columns", [])

    field_mapping = {
        "shift_date": "Date of Shift",
        "start_time": "Start Time",
        "end_time": "End Time",
        "company": "Company",
        "town": "Town",
        "postcode": "Postcode",
        "booking_source": "Booking Source",
        "rate": "Rate (GBP)",
    }

    if request.method == "POST":
        column_mapping = {}
        for field in field_mapping.keys():
            selected_column = request.form.get(field)
            if selected_column:
                column_mapping[field] = selected_column

        session["column_mapping"] = column_mapping

        return redirect(url_for("confirm_import"))

    return render_template("map_columns.html", columns=columns, field_mapping=field_mapping)

# Update Shift Time (Date, Start Time, End Time)
@app.route('/shift/<int:shift_id>/update_time', methods=['POST'])
@login_required
def update_shift_time(shift_id):
    shift_date = request.form.get("shift_date")
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")

    conn = get_db_connection()
    conn.execute(
        "UPDATE shifts SET shift_date = ?, start_time = ?, end_time = ? WHERE id = ? AND user_id = ?",
        (shift_date, start_time, end_time, shift_id, current_user.id)
    )
    conn.commit()
    conn.close()

    flash("Shift date and time updated successfully!", "success")
    return redirect(url_for("view_shift", shift_id=shift_id))

# Update Shift Rate
@app.route('/shift/<int:shift_id>/update_rate', methods=['POST'])
@login_required
def update_shift_rate(shift_id):
    rate = request.form.get("rate")

    conn = get_db_connection()
    conn.execute(
        "UPDATE shifts SET rate = ? WHERE id = ? AND user_id = ?",
        (rate, shift_id, current_user.id)
    )
    conn.commit()
    conn.close()

    flash("Shift rate updated successfully!", "success")
    return redirect(url_for("view_shift", shift_id=shift_id))

# Update Shift Location (Town and Postcode)
@app.route('/shift/<int:shift_id>/update_location', methods=['POST'])
@login_required
def update_shift_location(shift_id):
    company = request.form.get("company")
    company_other = request.form.get("companyOther").strip() if request.form.get("companyOther") else ""

    booking_source = request.form.get("booking_source")
    booking_source_other = request.form.get("bookingSourceOther").strip() if request.form.get("bookingSourceOther") else ""

    # If "Other" was selected, use the custom input instead
    if company == "OTHER" and company_other:
        company = company_other
    if booking_source == "OTHER" and booking_source_other:
        booking_source = booking_source_other

    town = request.form.get("town")
    postcode = request.form.get("postcode")

    conn = get_db_connection()
    conn.execute(
        "UPDATE shifts SET company = ?, town = ?, postcode = ?, booking_source = ? WHERE id = ? AND user_id = ?",
        (company, town, postcode, booking_source, shift_id, current_user.id)
    )
    conn.commit()
    conn.close()

    flash("Shift location updated successfully!", "success")
    return redirect(url_for("view_shift", shift_id=shift_id))

# Update Company & Booking Source (using dropdowns)
@app.route('/shift/<int:shift_id>/update_company', methods=['POST'])
@login_required
def update_shift_company(shift_id):
    company = request.form.get("company")
    booking_source = request.form.get("booking_source")
    conn = get_db_connection()
    conn.execute(
        "UPDATE shifts SET company = ?, booking_source = ? WHERE id = ? AND user_id = ?",
        (company, booking_source, shift_id, current_user.id)
    )
    conn.commit()
    conn.close()
    flash("Shift company and booking source updated successfully!", "success")
    return redirect(url_for("view_shift", shift_id=shift_id))

# Update Shift Status
@app.route('/shift/<int:shift_id>/update_status', methods=['POST'])
@login_required
def update_shift_status(shift_id):
    status = request.form.get("status")
    on_time = request.form.get("on_time")
    minutes_late = request.form.get("minutes_late")

    # Convert on_time value to boolean
    was_on_time = True if on_time == "yes" else False
    minutes_late = int(minutes_late) if on_time == "no" and minutes_late else 0

    conn = get_db_connection()
    conn.execute(
        "UPDATE shifts SET status = ?, on_time = ?, minutes_late = ? WHERE id = ? AND user_id = ?",
        (status, was_on_time, minutes_late, shift_id, current_user.id)
    )
    conn.commit()
    conn.close()

    flash("Shift status updated successfully!", "success")
    return redirect(url_for("view_shift", shift_id=shift_id))

# Route: Confirm Import and Save to Database
@app.route("/confirm_import", methods=["GET", "POST"])
@login_required
def confirm_import():
    if "uploaded_file" not in session or "column_mapping" not in session:
        flash("No file uploaded or mapping missing", "danger")
        return redirect(url_for("import_shifts"))

    file_path = session["uploaded_file"]
    column_mapping = session["column_mapping"]

    # Read the Excel file and map columns
    df = pd.read_excel(file_path, engine="openpyxl")
    mapped_data = df[list(column_mapping.values())].rename(columns={v: k for k, v in column_mapping.items()})

    # Check for missing shift dates
    if mapped_data["shift_date"].isna().sum() > 0:
        flash("Error: Some rows have missing shift dates. Please check your Excel file.", "danger")
        return redirect(url_for("map_columns"))

    if request.method == "POST":
        conn = get_db_connection()
        try:
            for _, row in mapped_data.iterrows():
                shift_date = row["shift_date"]
                start_time = row["start_time"]
                company = row["company"]

                # Ensure shift_date is not null
                if pd.isna(shift_date) or shift_date == "":
                    flash("Error: Some shifts are missing shift dates. Please check your Excel file.", "danger")
                    return redirect(url_for("confirm_import"))

                # Convert values to correct format
                shift_date_str = shift_date.strftime("%Y-%m-%d") if pd.notna(shift_date) else None
                start_time_str = start_time.strftime("%H:%M") if pd.notna(start_time) else None
                end_time_str = row["end_time"].strftime("%H:%M") if pd.notna(row["end_time"]) else None
                rate_value = float(row["rate"]) if pd.notna(row["rate"]) else 0.0

                # Check if the shift already exists to prevent duplicates
                existing_shift = conn.execute(
                    """
                    SELECT * FROM shifts WHERE user_id = ? AND shift_date = ? AND start_time = ? AND company = ?
                    """,
                    (current_user.id, shift_date_str, start_time_str, company),
                ).fetchone()

                if existing_shift:
                    flash(f"Duplicate shift found for {shift_date_str} at {start_time_str} ({company}). Skipping import.", "warning")
                    continue  # Skip this shift

                # Insert new shift
                conn.execute(
                    """
                    INSERT INTO shifts (user_id, shift_date, start_time, end_time, company, town, postcode, booking_source, rate)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        current_user.id,
                        shift_date_str,
                        start_time_str,
                        end_time_str,
                        company,
                        row["town"],
                        row["postcode"],
                        row["booking_source"],
                        rate_value,
                    ),
                )

            conn.commit()
            flash("Shifts imported successfully!", "success")

        except sqlite3.OperationalError as e:
            flash(f"Database error: {e}", "danger")
        finally:
            conn.close()
            # Remove session variables after successful import
            session.pop("uploaded_file", None)
            session.pop("columns", None)
            session.pop("column_mapping", None)

        return redirect(url_for("index"))

    return render_template("confirm_import.html", mapped_data=mapped_data.to_dict(orient="records"))

import requests
from datetime import datetime

HERE_API_KEY = "WLI5u6L_H2Mf-zMADXD5S2sXjJG3M4XDnly8PIyLcjI"

def get_coordinates(postcode, api_key=HERE_API_KEY):
    """Uses HERE Geocoding API to get the latitude and longitude for a postcode."""
    url = f"https://geocode.search.hereapi.com/v1/geocode?q={postcode}&apiKey={api_key}"
    response = requests.get(url)
    if response.status_code != 200:
        return None
    data = response.json()
    try:
        item = data["items"][0]
        lat = item["position"]["lat"]
        lng = item["position"]["lng"]
        return (lat, lng)
    except (KeyError, IndexError):
        return None

def get_route_alternatives(origin_coords, dest_coords, departure_time):
    """Uses HERE Routing API to get multiple route alternatives.
       Returns a list of dictionaries with the encoded polyline and summary data."""
    dep_time_iso = departure_time.isoformat()
    url = (
        f"https://router.hereapi.com/v8/routes?transportMode=car&"
        f"origin={origin_coords[0]},{origin_coords[1]}&"
        f"destination={dest_coords[0]},{dest_coords[1]}&"
        f"return=polyline,summary&alternatives=3&departureTime={dep_time_iso}&apiKey={HERE_API_KEY}"
    )
    response = requests.get(url)
    if response.status_code != 200:
        return []
    data = response.json()
    routes = []
    try:
        for route in data["routes"]:
            section = route["sections"][0]
            polyline = section["polyline"]
            summary = section["summary"]
            routes.append({"polyline": polyline, "summary": summary})
    except (KeyError, IndexError):
        return []
    return routes


def get_journey_time(origin_postcode, dest_postcode, api_key=HERE_API_KEY):
    """Get journey time (minutes) and distance (km) between two postcodes using HERE Routing API."""
    origin_coords = get_coordinates(origin_postcode, api_key)
    dest_coords = get_coordinates(dest_postcode, api_key)
    if not origin_coords or not dest_coords:
        return None
    url = (
        f"https://router.hereapi.com/v8/routes?transportMode=car&"
        f"origin={origin_coords[0]},{origin_coords[1]}&"
        f"destination={dest_coords[0]},{dest_coords[1]}&"
        f"return=summary&apiKey={api_key}"
    )
    r = requests.get(url)
    if r.status_code != 200:
        return None
    try:
        data = r.json()
        summary = data["routes"][0]["sections"][0]["summary"]
        duration = summary["duration"]  # in seconds
        distance = summary["length"]    # in meters
        journey_minutes = int(round(duration / 60))
        journey_km = round(distance / 1000, 2)
        return {"minutes": journey_minutes, "distance": journey_km}
    except (KeyError, IndexError):
        return None







if __name__ == '__main__':
    app.run(debug=True)
