import os
import time
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super_maxfiy_kalit_soz'

# Rasmlar va Baza sozlamalari
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///news.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
db = SQLAlchemy(app)

# --- MA'LUMOTLAR BAZASI MODELLARI ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_main_admin = db.Column(db.Boolean, default=False) # Asosiy admin bayrog'i
    is_blocked = db.Column(db.Boolean, default=False)    # Bloklanganlik holati

class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(200), nullable=True)

# Baza va Main Adminni yaratish
with app.app_context():
    db.create_all()
    main_admin = User.query.filter_by(username='admin').first()
    if not main_admin:
        main_admin = User(
            username='admin', 
            password=generate_password_hash('admin123'), 
            is_admin=True,
            is_main_admin=True,
            is_blocked=False
        )
        db.session.add(main_admin)
        db.session.commit()

# --- YO'NALISHLAR (ROUTES) ---

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Sessiyadagi foydalanuvchi bloklanmaganini tekshirish
    user = User.query.get(session['user_id'])
    if not user or user.is_blocked:
        session.clear()
        return redirect(url_for('login'))

    all_news = News.query.order_by(News.id.desc()).all()
    return render_template('index.html', news_list=all_news)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            error = "Bu foydalanuvchi nomi band!"
        else:
            new_user = User(
                username=username,
                password=generate_password_hash(password),
                is_admin=False
            )
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))

    return render_template('register.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            if user.is_blocked:
                error = "Sizning hisobingiz bloklangan! Admin bilan bog'laning."
            else:
                session['user_id'] = user.id
                session['username'] = user.username
                session['is_admin'] = user.is_admin
                session['is_main_admin'] = user.is_main_admin
                return redirect(url_for('index'))
        else:
            error = "Login yoki parol xato kiritildi!"
            
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- ADMIN PANEL & YANGILIKLAR ---

@app.route('/admin')
def admin_panel():
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    all_news = News.query.order_by(News.id.desc()).all()
    return render_template('admin.html', news_list=all_news)

@app.route('/admin/add', methods=['GET', 'POST'])
def add_news():
    if not session.get('is_admin'):
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        file = request.files.get('image')

        image_filename = None
        if file and file.filename != '':
            ext = os.path.splitext(file.filename)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                image_filename = f"news_{int(time.time())}{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))

        new_item = News(title=title, content=content, image=image_filename)
        db.session.add(new_item)
        db.session.commit()
        return redirect(url_for('admin_panel'))

    return render_template('add.html')

@app.route('/admin/edit/<int:id>', methods=['GET', 'POST'])
def edit_news(id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))

    news_item = News.query.get_or_404(id)

    if request.method == 'POST':
        news_item.title = request.form['title']
        news_item.content = request.form['content']
        file = request.files.get('image')

        if file and file.filename != '':
            ext = os.path.splitext(file.filename)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                image_filename = f"news_{int(time.time())}{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
                news_item.image = image_filename

        db.session.commit()
        return redirect(url_for('admin_panel'))

    return render_template('edit.html', news=news_item)

@app.route('/admin/delete/<int:id>')
def delete_news(id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))

    news_item = News.query.get_or_404(id)
    if news_item.image:
        img_path = os.path.join(app.config['UPLOAD_FOLDER'], news_item.image)
        if os.path.exists(img_path):
            os.remove(img_path)

    db.session.delete(news_item)
    db.session.commit()
    return redirect(url_for('admin_panel'))

# --- FOYDALANUVCHILARNI BOSHQARISH (ADMIN) ---

@app.route('/admin/users')
def manage_users():
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    
    users = User.query.order_by(User.id.asc()).all()
    return render_template('users.html', users=users)

@app.route('/admin/users/add', methods=['GET', 'POST'])
def add_user():
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role'] # 'user' yoki 'admin'

        if User.query.filter_by(username=username).first():
            error = "Bu foydalanuvchi nomi allaqachon mavjud!"
        else:
            is_admin_flag = True if role == 'admin' else False
            new_user = User(
                username=username,
                password=generate_password_hash(password),
                is_admin=is_admin_flag,
                is_main_admin=False,
                is_blocked=False
            )
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('manage_users'))

    return render_template('add_user.html', error=error)

@app.route('/admin/users/toggle-block/<int:id>')
def toggle_block_user(id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))

    user = User.query.get_or_404(id)

    # Main admint yoki o'zini bloklash taqiqlanadi
    if user.is_main_admin or user.id == session['user_id']:
        return redirect(url_for('manage_users'))

    user.is_blocked = not user.is_blocked
    db.session.commit()
    return redirect(url_for('manage_users'))

@app.route('/admin/users/delete/<int:id>')
def delete_user(id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))

    user = User.query.get_or_404(id)

    # Main adminni yoki o'zini o'chirish taqiqlanadi
    if user.is_main_admin or user.id == session['user_id']:
        return redirect(url_for('manage_users'))

    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('manage_users'))

if __name__ == '__main__':
    app.run(debug=True)