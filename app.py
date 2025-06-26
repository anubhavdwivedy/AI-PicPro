import os
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from rembg import remove
from PIL import Image, ImageDraw
import openai
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# -------------------- Config --------------------
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default_secret_key')

# Use /tmp directory for uploads (Render requires this)
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['PROCESSED_FOLDER'] = '/tmp/processed'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
openai.api_key = os.getenv('OPENAI_API_KEY')

# -------------------- Models --------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class FileHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(300))
    action = db.Column(db.String(100))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

# -------------------- Auth Setup --------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------- Routes --------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        raw_password = request.form['password']
        if User.query.filter_by(username=username).first():
            return 'Username already exists'
        hashed_password = generate_password_hash(raw_password)
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        raw_password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, raw_password):
            login_user(user)
            return redirect(url_for('dashboard'))
        return 'Invalid credentials'
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    history = FileHistory.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', history=history)

# -------------------- File Features --------------------
@app.route('/upload', methods=['POST'])
@login_required
def upload():
    file = request.files['image']
    path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(path)
    record = FileHistory(filename=file.filename, action='Uploaded', user_id=current_user.id)
    db.session.add(record)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/remove_bg/<filename>')
@login_required
def remove_bg(filename):
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    with open(input_path, 'rb') as inp:
        output = remove(inp.read())
    out_path = os.path.join(app.config['PROCESSED_FOLDER'], f'nobg_{filename}')
    with open(out_path, 'wb') as out_file:
        out_file.write(output)
    record = FileHistory(filename=f'nobg_{filename}', action='Background Removed', user_id=current_user.id)
    db.session.add(record)
    db.session.commit()
    return send_from_directory(app.config['PROCESSED_FOLDER'], f'nobg_{filename}', as_attachment=True)

@app.route('/convert/<filename>/<format>')
@login_required
def convert_format(filename, format):
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    img = Image.open(input_path)
    output_filename = f'converted_{os.path.splitext(filename)[0]}.{format}'
    out_path = os.path.join(app.config['PROCESSED_FOLDER'], output_filename)
    img.save(out_path, format=format.upper())
    record = FileHistory(filename=output_filename, action=f'Converted to {format}', user_id=current_user.id)
    db.session.add(record)
    db.session.commit()
    return send_from_directory(app.config['PROCESSED_FOLDER'], output_filename, as_attachment=True)

@app.route('/watermark/<filename>')
@login_required
def watermark(filename):
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    output_path = os.path.join(app.config['PROCESSED_FOLDER'], f'watermarked_{filename}')
    img = Image.open(input_path).convert("RGBA")
    watermark_layer = Image.new("RGBA", img.size)
    draw = ImageDraw.Draw(watermark_layer)
    draw.text((10, 10), "Your Watermark", fill=(255,255,255,128))
    combined = Image.alpha_composite(img, watermark_layer)
    combined.save(output_path)
    record = FileHistory(filename=f'watermarked_{filename}', action='Watermarked', user_id=current_user.id)
    db.session.add(record)
    db.session.commit()
    return send_from_directory(app.config['PROCESSED_FOLDER'], f'watermarked_{filename}', as_attachment=True)

# -------------------- Download --------------------
@app.route('/download/<filename>')
@login_required
def download(filename):
    return send_from_directory(app.config['PROCESSED_FOLDER'], filename, as_attachment=True)

# -------------------- Chat Assistant --------------------
@app.route('/chat', methods=['POST'])
@login_required
def chat():
    user_message = request.json.get('message')
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": user_message}]
        )
        reply = response.choices[0].message.content
        return jsonify({'reply': reply})
    except Exception as e:
        return jsonify({'error': str(e)})

# -------------------- DB Init --------------------
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
