import os
import time
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

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
    is_main_admin = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)

class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(200), nullable=True)

# Baza va Asosiy Adminni yaratish
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

# --- YORDAMCHI FUNKSIYALAR ---

def is_allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS

# --- YO'NALISHLAR (ROUTES) ---

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user or user.is_blocked:
        session.clear()
        flash("Hisobingiz mavjud emas yoki bloklangan!", "danger")
        return redirect(url_for('login'))

    all_news = News.query.order_by(News.id.desc()).all()
    return render_template('index.html', news_list=all_news)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            error = "Barcha maydonlarni to'ldiring!"
        elif User.query.filter_by(username=username).first():
            error = "Bu foydalanuvchi nomi band!"
        else:
            new_user = User(
                username=username,
                password=generate_password_hash(password),
                is_admin=False
            )
            db.session.add(new_user)
            db.session.commit()
            flash("Ro'yxatdan muvaffaqiyatli o'tdingiz! Tizimga kiring.", "success")
            return redirect(url_for('login'))

    return render_template('register.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
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

# --- FOYDALANUVCHINING PAROLINI O'ZGARTIRISHI ---

@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    error = None
    if request.method == 'POST':
        old_password = request.form.get('old_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        user = User.query.get(session['user_id'])

        if not check_password_hash(user.password, old_password):
            error = "Eski parol noto'g'ri kiritildi!"
        elif new_password != confirm_password:
            error = "Yangi parollar bir-biriga mos kelmadi!"
        elif len(new_password) < 4:
            error = "Yangi parol kamida 4 ta belgidan iborat bo'lishi kerak!"
        else:
            user.password = generate_password_hash(new_password)
            db.session.commit()
            flash("Parolingiz muvaffaqiyatli o'zgartirildi!", "success")
            return redirect(url_for('index'))

    return render_template('change_password.html', error=error)

# --- FOYDALANUVCHINING LOGIN VA PAROLINI BIRGA O'ZGARTIRISHI ---

@app.route('/change-credentials', methods=['GET', 'POST'])
def change_credentials():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    error = None

    if request.method == 'POST':
        new_username = request.form.get('new_username', '').strip()
        old_password = request.form.get('old_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not check_password_hash(user.password, old_password):
            error = "Eski parol noto'g'ri kiritildi!"
        elif new_username != user.username and User.query.filter_by(username=new_username).first():
            error = "Bu foydalanuvchi nomi allaqachon band!"
        elif new_password and new_password != confirm_password:
            error = "Yangi parollar bir-biriga mos kelmadi!"
        elif new_password and len(new_password) < 4:
            error = "Yangi parol kamida 4 ta belgidan iborat bo'lishi kerak!"
        else:
            user.username = new_username
            session['username'] = new_username

            if new_password:
                user.password = generate_password_hash(new_password)

            db.session.commit()
            flash("Profil ma'lumotlari muvaffaqiyatli yangilandi!", "success")
            return redirect(url_for('index'))

    return render_template('change_credentials.html', current_user=user, error=error)

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
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        file = request.files.get('image')

        image_filename = None
        if file and file.filename != '':
            ext = os.path.splitext(file.filename)[1].lower()
            if is_allowed_file(file.filename):
                image_filename = f"news_{int(time.time())}{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))

        new_item = News(title=title, content=content, image=image_filename)
        db.session.add(new_item)
        db.session.commit()
        flash("Yangilik muvaffaqiyatli qo'shildi!", "success")
        return redirect(url_for('admin_panel'))

    return render_template('add.html')

@app.route('/admin/edit/<int:id>', methods=['GET', 'POST'])
def edit_news(id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))

    news_item = News.query.get_or_404(id)

    if request.method == 'POST':
        news_item.title = request.form.get('title', '').strip()
        news_item.content = request.form.get('content', '').strip()
        file = request.files.get('image')

        if file and file.filename != '':
            ext = os.path.splitext(file.filename)[1].lower()
            if is_allowed_file(file.filename):
                if news_item.image:
                    old_img_path = os.path.join(app.config['UPLOAD_FOLDER'], news_item.image)
                    if os.path.exists(old_img_path):
                        os.remove(old_img_path)

                image_filename = f"news_{int(time.time())}{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
                news_item.image = image_filename

        db.session.commit()
        flash("Yangilik tahrirlandi!", "info")
        return redirect(url_for('admin_panel'))

    return render_template('edit.html', news=news_item)

@app.route('/admin/delete/<int:id>', methods=['POST', 'GET'])
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
    flash("Yangilik o'chirildi!", "warning")
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
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role')

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
            flash("Yangi foydalanuvchi qo'shildi!", "success")
            return redirect(url_for('manage_users'))

    return render_template('add_user.html', error=error)

@app.route('/admin/users/toggle-block/<int:id>', methods=['POST', 'GET'])
def toggle_block_user(id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))

    user = User.query.get_or_404(id)

    if user.is_main_admin or user.id == session.get('user_id'):
        flash("Asosiy adminni yoki o'zingizni bloklay olmaysiz!", "danger")
        return redirect(url_for('manage_users'))

    user.is_blocked = not user.is_blocked
    db.session.commit()
    flash(f"Foydalanuvchi {user.username} holati o'zgartirildi.", "info")
    return redirect(url_for('manage_users'))

@app.route('/admin/users/delete/<int:id>', methods=['POST', 'GET'])
def delete_user(id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))

    user = User.query.get_or_404(id)

    if user.is_main_admin or user.id == session.get('user_id'):
        flash("Asosiy adminni yoki o'zingizni o'chira olmaysiz!", "danger")
        return redirect(url_for('manage_users'))

    db.session.delete(user)
    db.session.commit()
    flash("Foydalanuvchi o'chirib tashlandi!", "warning")
    return redirect(url_for('manage_users'))

@app.route('/admin/users/reset-password/<int:id>', methods=['GET', 'POST'])
def admin_reset_password(id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))

    user = User.query.get_or_404(id)
    error = None

    if request.method == 'POST':
        new_password = request.form.get('new_password', '').strip()

        if not new_password or len(new_password) < 4:
            error = "Parol kamida 4 ta belgidan iborat bo'lishi kerak!"
        else:
            user.password = generate_password_hash(new_password)
            db.session.commit()
            flash(f"{user.username} uchun yangi parol o'rnatildi!", "success")
            return redirect(url_for('manage_users'))

    return render_template('admin_reset_password.html', target_user=user, error=error)

if __name__ == '__main__':
    app.run(debug=True)