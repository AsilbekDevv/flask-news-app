from gevent import monkey
monkey.patch_all()

import os
import time
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = 'super_maxfiy_kalit_soz'

# Socket.IO ni ulash (Render uchun cors va async_mode sozlamasi bilan)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Rasmlar va Baza sozlamalari
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///news.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
db = SQLAlchemy(app)

# O'zbekiston vaqtini olish uchun yordamchi funksiya (UTC+5)
def get_uzbekistan_time():
    uz_time = datetime.now(timezone.utc) + timedelta(hours=5)
    return uz_time

# --- MA'LUMOTLAR BAZASI MODELLARI ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_main_admin = db.Column(db.Boolean, default=False) 
    is_blocked = db.Column(db.Boolean, default=False)    

    @property
    def user_code(self):
        return 1000 + self.id

class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(200), nullable=True)

# Chat tarixi uchun baza modeli
class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=get_uzbekistan_time)

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
    
    user = User.query.get(session['user_id'])
    if not user or user.is_blocked:
        session.clear()
        return redirect(url_for('login'))

    all_news = News.query.order_by(News.id.desc()).all()
    return render_template('index.html', news_list=all_news)


@app.route('/news/<int:id>')
def news_detail(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user or user.is_blocked:
        session.clear()
        return redirect(url_for('login'))

    news_item = News.query.get_or_404(id)
    return render_template('details.html', news=news_item)

# --- CHAT YO'NALISHLARI ---

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user or user.is_blocked:
        session.clear()
        return redirect(url_for('login'))
    
    messages = ChatMessage.query.order_by(ChatMessage.timestamp.asc()).all()
    return render_template('chat.html', messages=messages)


@socketio.on('send_message')
def handle_message(data):
    if 'user_id' not in session:
        return

    user_id = session['user_id']
    username = session.get('username', 'Anonim')
    message_text = data.get('msg')

    if message_text:
        current_time = get_uzbekistan_time()

        new_msg = ChatMessage(
            user_id=user_id, 
            username=username, 
            message=message_text,
            timestamp=current_time
        )
        db.session.add(new_msg)
        db.session.commit()

        time_str = current_time.strftime('%H:%M')

        emit('receive_message', {
            'user': username, 
            'msg': message_text,
            'time': time_str
        }, broadcast=True)

@socketio.on('request_clear_chat')
def handle_clear_chat():
    if session.get('is_admin'):
        try:
            ChatMessage.query.delete()
            db.session.commit()
            emit('chat_cleared', broadcast=True)
        except Exception as e:
            db.session.rollback()

# --- PROFIL YO'NALISHLARI (YANGI) ---

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user or user.is_blocked:
        session.clear()
        return redirect(url_for('login'))

    error = None
    success = None

    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        new_password = request.form.get('password', '').strip()

        # Login band emasligini tekshirish (foydalanuvchining o'zidan tashqari)
        existing_user = User.query.filter(User.username == new_username, User.id != user.id).first()
        
        if existing_user:
            error = "Bu login allaqachon band! Iltimos, boshqa login tanlang."
        else:
            if new_username:
                user.username = new_username
                session['username'] = new_username  # Sessiyadagi nomni ham yangilaymiz
            
            # Agar yangi parol yozilgan bo'lsa, uni hashlash
            if new_password:
                user.password = generate_password_hash(new_password)
            
            db.session.commit()
            
            # Agar chatdagi xabarlari bo'lsa, eski nomda qolib ketmasligi uchun ularni ham yangilaymiz
            ChatMessage.query.filter_by(user_id=user.id).update({'username': new_username})
            db.session.commit()
            
            success = "Profil ma'lumotlaringiz muvaffaqiyatli saqlandi!"

    return render_template('profile.html', user=user, error=error, success=success)

@app.route('/profile/delete', methods=['POST'])
def delete_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if user:
        if user.is_main_admin:
            flash("Asosiy admin profilini o'chirib bo'lmaydi!", "danger")
            return redirect(url_for('profile'))
        
        # O'chirilayotgan foydalanuvchining chatdagi xabarlarini ham bazadan tozalaymiz (xatolik bermasligi uchun)
        ChatMessage.query.filter_by(user_id=user.id).delete()
        
        # Foydalanuvchini bazadan o'chirish
        db.session.delete(user)
        db.session.commit()
    
    session.clear()
    return redirect(url_for('login'))

# --- RO'YXATDAN O'TISH ---

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

            # --- BILDIRISHNOMA YUBORISH ---
            now_time = get_uzbekistan_time().strftime('%H:%M')
            socketio.emit('notification_new_user', {
                'username': username,
                'time': now_time
            })
            # ------------------------------

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
        role = request.form['role']

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

    if user.is_main_admin or user.id == session['user_id']:
        return redirect(url_for('manage_users'))

    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('manage_users'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)