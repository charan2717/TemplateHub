from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import sqlite3
import zipfile
import uuid

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# --- Configuration ---
UPLOAD_FOLDER = 'static/uploads'
THUMBNAIL_FOLDER = 'static/thumbnails'
PREVIEW_FOLDER = 'static/previews'
ALLOWED_EXTENSIONS = {'zip'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['THUMBNAIL_FOLDER'] = THUMBNAIL_FOLDER
app.config['PREVIEW_FOLDER'] = PREVIEW_FOLDER

# Create necessary folders
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(THUMBNAIL_FOLDER, exist_ok=True)
os.makedirs(PREVIEW_FOLDER, exist_ok=True)

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            filename TEXT NOT NULL,  -- stores preview folder ID
            thumbnail TEXT NOT NULL,
            uploader TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect('database.db')  # Replace with your DB filename
    conn.row_factory = sqlite3.Row
    return conn

# --- Helpers ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Routes ---
@app.route('/')
def home():
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()
    cur.execute("SELECT * FROM templates ORDER BY id DESC")
    templates = cur.fetchall()
    conn.close()
    return render_template('index.html', templates=templates)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        try:
            conn = sqlite3.connect('database.db')
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            conn.close()
            return redirect('/login')
        except sqlite3.IntegrityError:
            return "⚠️ Username already exists"
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('database.db')
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['username'] = username
            return redirect('/')
        else:
            return "❌ Invalid credentials"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect('/')

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'username' not in session:
        return redirect('/login')

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form['description']
        file = request.files.get('file')
        thumbnail = request.files['thumbnail']

        if file and allowed_file(file.filename):
            # Save thumbnail
            thumbname = secure_filename(thumbnail.filename)
            thumbpath = os.path.join(app.config['THUMBNAIL_FOLDER'], thumbname)
            thumbnail.save(thumbpath)

            # Generate unique preview folder
            preview_id = str(uuid.uuid4())
            preview_path = os.path.join(app.config['PREVIEW_FOLDER'], preview_id)
            os.makedirs(preview_path, exist_ok=True)

            # Save zip temporarily
            zip_temp_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
            file.save(zip_temp_path)

            # Extract zip to preview folder
            try:
                with zipfile.ZipFile(zip_temp_path, 'r') as zip_ref:
                    zip_ref.extractall(preview_path)
            except zipfile.BadZipFile:
                return "❌ Invalid ZIP file"

            os.remove(zip_temp_path)  # Remove temp zip

            # Insert into database
            conn = sqlite3.connect('database.db')
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO templates (title, description, filename, thumbnail, uploader)
                VALUES (?, ?, ?, ?, ?)
            ''', (title, description, preview_id, thumbname, session['username']))
            conn.commit()
            conn.close()

            return redirect('/')

    return render_template('upload.html')

@app.route('/template/<int:id>')
def view_template(id):
    conn = get_db_connection()
    template = conn.execute('SELECT * FROM templates WHERE id = ?', (id,)).fetchone()
    conn.close()

    preview_dir = os.path.join('static', 'previews', template[3])
    html_code = css_code = js_code = ''

    try:
        with open(os.path.join(preview_dir, 'index.html'), 'r', encoding='utf-8') as f:
            html_code = f.read()
    except: pass

    try:
        with open(os.path.join(preview_dir, 'style.css'), 'r', encoding='utf-8') as f:
            css_code = f.read()
    except: pass

    try:
        with open(os.path.join(preview_dir, 'script.js'), 'r', encoding='utf-8') as f:
            js_code = f.read()
    except: pass

    return render_template('view_template.html', template=template, html_code=html_code, css_code=css_code, js_code=js_code)


@app.route('/download/<preview_id>')
def download(preview_id):
    path = os.path.join(app.config['PREVIEW_FOLDER'], preview_id)
    return send_from_directory(path, 'index.html')

# --- Run ---
if __name__ == '__main__':
    app.run(debug=True)
