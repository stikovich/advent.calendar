# app.py
import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt'}

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db():
    if 'DATABASE_URL' in os.environ:
        # На Render или Heroku — PostgreSQL
        conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=DictCursor)
        conn.set_session(autocommit=True)
    else:
        # Локально — SQLite
        import sqlite3
        conn = sqlite3.connect('database.db', timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL;')
    return conn

# --- Инициализация БД ---
def init_db():
    if 'DATABASE_URL' in os.environ:
        # Работаем с PostgreSQL
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cursor = conn.cursor()

        # Создание таблиц
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS progress (
                user_id INTEGER,
                day INTEGER,
                opened_at TIMESTAMP,
                PRIMARY KEY (user_id, day)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                day INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT,
                hint TEXT,
                image_url TEXT,
                video_url TEXT,
                is_published INTEGER DEFAULT 0,
                points_free INTEGER DEFAULT 0,
                points_global INTEGER DEFAULT 0,
                is_paid INTEGER DEFAULT 0,
                response_type TEXT DEFAULT 'file'
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS points (
                user_id INTEGER PRIMARY KEY,
                free_points INTEGER DEFAULT 0,
                paid_points INTEGER DEFAULT 0
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS submissions_day (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                day INTEGER,
                file_url TEXT,
                text_response TEXT,
                submitted_at TIMESTAMP,
                status TEXT DEFAULT 'pending'
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rewards (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                reward_type TEXT,
                awarded_at TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS global_progress (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                total_points INTEGER DEFAULT 0
            )
        ''')

        # Вставка начального значения
        cursor.execute('''
            INSERT INTO global_progress (id, total_points)
            VALUES (1, 0)
            ON CONFLICT (id) DO NOTHING
        ''')

        # Примеры заданий
        sample_tasks = [
            (1, 'Вопросики', 'Ответьте на вопросы:', 'Вспомните 1 квест.', None, None, 1, 30, 5, 0, 'text'),
            (2, 'Письмо', 'Напишите письмо деду морозу.', 'Он существует!', None, None, 1, 20, 5, 0, 'text'),
            (3, 'Основной канал', 'Подпишитесь на канал компании.', 'Спасибо от SMOKE!TYT', None, None, 1, 25, 5, 0, 'file'),
            (4, 'Рисование', 'Нарисуйте новогоднюю елочку.', 'Главное от души.', None, None, 1, 15, 5, 0, 'file'),
            (5, 'Сплетни', 'Расскажите 3-м друзьям об этом квесте, если заинтересует, то писать менеджеру.', 'Говорите убедительно. Особенно про подарки.', None, None, 1, 50, 5, 0, 'file'),
            (6, 'О, заказик', 'Сделайте заказ в магазине (любой).', 'Даже самое дешевое.', None, None, 1, 0, 5, 100, 'file'),
            (7, 'Что ждете?', 'Какие у вас ожидания от ближайшего теста продукции?', 'Говорите честно.', None, None, 1, 30, 5, 0, 'text'),
            (8, 'Запомнили?', 'Напишите о самом запоминающемся событии за 2025.', 'Интересное событие.', None, None, 1, 15, 5, 0, 'text'),
            (9, 'Пусть сбудется!', 'Какой вы видите (или хотели бы видеть) нашу компанию в 2026?', 'Мы учтем ваши пожелания.', None, None, 1, 30, 5, 0, 'text'),
            (10, 'С Новым Годом!', 'Поздравьте с НГ Харриса.', 'Ему будет приятно, а для вас в конце все старания окупяться.', None, None, 1, 0, 0, 150, 'file'),
            (11, 'Элиза?', 'Ваше мнение, кто такая Элиза?', 'Она живая.', None, None, 1, 30, 5, 0, 'text'),
            (12, 'Мама - это святое', 'Сделайте открытку - поздравление с наступающим Новым годом своими руками и подарите маме.', 'Маме будет приятно.', None, None, 1, 25, 5, 0, 'file'),
            (13, 'Разгадай-ка', 'Разгадайте загадку и напишите ответ.', 'Ответ проще, чем вы думаете.', None, None, 1, 15, 5, 0, 'text'),
            (14, 'С Новым Годом!', 'Поздравьте с НГ Эдварда.', 'Ему будет приятно, а для вас в конце все старания окупяться.', None, None, 1, 0, 5, 150, 'file'),
            (15, 'Подписочка', 'Подпишитесь на канал.', 'Давайте поддержим музыканта.', None, None, 1, 30, 5, 0, 'file'),
            (16, 'С Новым Годом!', 'Напишите поздравление команде.', 'Нам будет приятно почитать ваши поздравления.', None, None, 1, 30, 5, 0, 'text'),
            (17, 'С Новым Годом!', 'Поздравьте с НГ команду.', 'Нам будет приятно, а для вас в конце все старания окупяться.', None, None, 1, 0, 5, 150, 'file'),
            (18, 'А это вам', 'ПОЗДРАВЛЕНИЕ ДОБАВИТЬ', 'С Новым Годом!', None, None, 1, 26, 5, 0, 'text'),
            (19, 'Под одеяльцом', 'Посмотрите Новогодний фильм. Напишите свой отзыв о нем.', 'Только не "Один дома".', None, None, 1, 15, 5, 0, 'text'),
            (20, 'Вкуснота', 'Напишите о своём любимом новогоднем блюде. Что это? И почему самое любимое?', 'Салатики, закусочки, ммм.', None, None, 1, 15, 5, 0, 'text'),
            (21, 'Друг или враг?', 'Напишите свое развернутое мнение о Харрисе.', 'Пишите то, что реально думаете.', None, None, 1, 30, 5, 0, 'text'),
            (22, 'Кто он?', 'Как вы считаете, кто такой на самом деле Эдвард Лимб?', 'Развернутиый ответ.', None, None, 1, 30, 5, 0, 'text'),
            (23, 'Ну мы же старалиииись.', 'Благодарность за квест', 'Мы потратили много сил и времени.', None, None, 1, 0, 5, 100, 'text'),
            (24, 'Елочка', 'Пришлите фото своей новогодней елки.', 'Наряженная.', None, None, 1, 15, 5, 0, 'file'),
            (25, 'Посчитаем', 'Какой возраст компании?', 'Не месяц.', None, None, 1, 20, 5, 0, 'text'),
            (26, 'Подарочки', 'Расскажите какие подарки получили на Новый год.', 'Много подарочков?', None, None, 1, 20, 5, 0, 'text'),
            (27, 'Хорошо?', 'Напишите свое мнение о том, как вы провели новогодние праздники.', 'Куда же без вредного.', None, None, 1, 15, 5, 1, 'text'),
            (28, 'Здоровая критика', 'Выскажите мнение про творчество.', 'Ему будет интерсно услышать честное мнение.', None, None, 1, 25, 5, 0, 'text'),
            (29, 'Надо проснуться', 'Купите кофе, пожалуйста.', 'В первый день не проснуться.', None, None, 1, 0, 5, 100, 'file'),
            (30, 'Тяжеловато', 'Расскажите, какого выходить на учебу/работу/другое, после новогодних праздников.', 'Тяжело, согласны.', None, None, 1, 20, 5, 0, 'text'),
            (31, 'Добиваем подарочки', 'Получи дополнительные баллы (чем больше донат, тем больше баллов, отличная возможность под конец добить баллы). 1 балл, за каждые 2₽.', 'Не упускайте возможность забрать максимальные призы.', None, None, 1, 0, 0, 0, 'file'),
        ]

        for task in sample_tasks:
            cursor.execute('''
                INSERT INTO tasks 
                (day, title, content, hint, image_url, video_url, is_published, points_free, points_global, is_paid, response_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (day) DO UPDATE SET
                title = EXCLUDED.title,
                content = EXCLUDED.content
            ''', task)

        # Админ
        cursor.execute('''
            INSERT INTO users (username, password, is_admin)
            VALUES ('admin', %s, 1)
            ON CONFLICT (username) DO NOTHING
        ''', (generate_password_hash('22551bdg'),))

        conn.commit()
        conn.close()

    else:
        # Локально — SQLite (как раньше)
        with sqlite3.connect('database.db') as conn:
            conn.execute('PRAGMA journal_mode=WAL;')
            cursor = conn.cursor()

# --- Функции ---
def get_global_points():
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT total_points FROM global_progress WHERE id = 1')
        row = cursor.fetchone()
        return row['total_points'] if row else 0
    finally:
        conn.close()

def get_user_points(user_id):
    if not user_id:
        return 0, 0
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT free_points, paid_points FROM points WHERE user_id = %s', (user_id,))
        row = cursor.fetchone()
        return (row['free_points'], row['paid_points']) if row else (0, 0)
    finally:
        conn.close()

def add_points(user_id, free_points, paid_points):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT free_points, paid_points FROM points WHERE user_id = %s', (user_id,))
        row = cursor.fetchone()
        if row:
            current_free, current_paid = row['free_points'], row['paid_points']
        else:
            current_free, current_paid = 0, 0

        new_free = min(1015, current_free + free_points)
        new_paid = min(1001, current_paid + paid_points)

        cursor.execute('''
            INSERT INTO points (user_id, free_points, paid_points)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
            SET free_points = EXCLUDED.free_points, paid_points = EXCLUDED.paid_points
        ''', (user_id, new_free, new_paid))
        conn.commit()

        check_rewards(user_id, conn)
    finally:
        conn.close()

def add_to_global_points(points):
    conn = get_db()
    try:
        current = get_global_points()  # уже с get_db()
        new_total = min(2026, current + points)
        cursor = conn.cursor()
        cursor.execute('UPDATE global_progress SET total_points = %s WHERE id = 1', (new_total,))
        conn.commit()
    finally:
        conn.close()

def get_reward_targets():
    return {
        'personal': [
            {'type': 'xalava', 'name': 'Бесплатная позиция в магазине из предложенных', 'points': 555},
            {'type': 'small', 'name': 'Маленький приз', 'points': 1276},
            {'type': 'merch', 'name': 'Брелок (мерч)', 'points': 1444},
            {'type': 'medium', 'name': 'Средний приз', 'points': 1651},
            {'type': 'large', 'name': 'Большой приз', 'points': 2026},
        ],
        'global': [
            {'type': 'sale', 'name': 'Б/У Aegis Hero 2 за 999р', 'points': 226},
            {'type': 'xalava', 'name': 'Скидка 50% в магазине', 'points': 777},
            {'type': 'certificate', 'name': 'Секретный приз', 'points': 1013},
        ]
    }

def get_reward_targets():
    return {
        'personal': [
            {'type': 'xalava', 'name': 'Бесплатная позиция в магазине из предложенных', 'points': 555},
            {'type': 'small', 'name': 'Маленький приз', 'points': 1276},
            {'type': 'merch', 'name': 'Брелок (мерч)', 'points': 1444},
            {'type': 'medium', 'name': 'Средний приз', 'points': 1651},
            {'type': 'large', 'name': 'Большой приз', 'points': 2026},
        ],
        'global': [
            {'type': 'sale', 'name': 'Б/У Aegis Hero 2 за 999р', 'points': 226},
            {'type': 'xalava', 'name': 'Скидка 50% в магазине', 'points': 777},
            {'type': 'certificate', 'name': 'Секретный приз', 'points': 1013},
        ]
    }

def mark_day_as_opened(user_id, day):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO progress (user_id, day, opened_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (user_id, day) DO NOTHING
        ''', (user_id, day))
        conn.commit()
    finally:
        conn.close()

def can_open_door(day):
    if day < 1 or day > 24:
        return False
    now = datetime.now()
    # День 1 = 1 декабря
    door_date = datetime(now.year, 12, 1) + timedelta(days=day - 1)
    # Сезон: с 1 декабря по 24 декабря
    start = datetime(now.year, 12, 1)
    end = datetime(now.year, 12, 24)
    return start <= door_date <= now <= end

def get_calendar_days():
    return [
        {'day': d, 'date': f'{d} декабря'} 
        for d in range(1, 25)
    ]

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.context_processor
def inject_functions():
    return {
        'can_open': can_open_door,  # теперь можно использовать в шаблоне
        'now': datetime.now()  # чтобы использовать {{ now.year }}
    }

# --- Маршруты ---
@app.before_request
def require_login():
    allowed_routes = ['login', 'register', 'static', 'index']
    if 'user_id' not in session and request.endpoint not in allowed_routes:
        return redirect(url_for('login'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calendar')
def calendar():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    free, paid = get_user_points(user_id)
    personal_total = free + paid
    global_total = get_global_points()

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT day FROM progress WHERE user_id = %s', (user_id,))
        opened_days = {row['day'] for row in cursor.fetchall()}

        cursor.execute('SELECT reward_type FROM rewards WHERE user_id = %s', (user_id,))
        awarded_rewards = {row['reward_type'] for row in cursor.fetchall()}
    finally:
        conn.close()

    # Доступные дни
    now = datetime.now().date()
    season_end = datetime(now.year, 12, 24).date()
    available_days = {
        day for day in range(1, 25)
        if (datetime(now.year, 12, 1) + timedelta(days=day - 1)).date() <= now <= season_end
    }

    reward_targets = get_reward_targets()

    return render_template(
        'calendar.html',
        user=session.get('username'),
        is_admin=session.get('is_admin', False),
        opened_days=opened_days,
        calendar_days=get_calendar_days(),
        can_open=can_open_door,
        free_points=free,
        paid_points=paid,
        personal_total=personal_total,
        global_total=global_total,
        available_days=available_days,
        reward_targets=reward_targets,
        awarded_rewards=awarded_rewards
    )

@app.route('/day/<int:day>', methods=['GET', 'POST'])
def view_day(day):
    if day < 1 or day > 24:
        flash('Нет такого дня.')
        return redirect(url_for('calendar'))
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tasks WHERE day = %s AND is_published = 1', (day,))
        task = cursor.fetchone()
        if not task:
            flash('Задание не опубликовано.')
            return redirect(url_for('calendar'))
        if not can_open_door(day):
            flash('День ещё не наступил.')
            return redirect(url_for('calendar'))

        cursor.execute('SELECT status FROM submissions_day WHERE user_id = %s AND day = %s', (user_id, day))
        submission = cursor.fetchone()
    finally:
        conn.close()

    if request.method == 'POST':
        if submission:
            flash('Вы уже отправили ответ.')
            return redirect(url_for('view_day', day=day))

        conn = get_db()
        try:
            file_url = None
            text_response = None

            if task['response_type'] == 'file':
                file = request.files['file']
                if file and allowed_file(file.filename):
                    filename = secure_filename(f"day{day}_user{user_id}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    file_url = f"uploads/{filename}"
                else:
                    flash('Некорректный файл.')
                    return redirect(url_for('view_day', day=day))
            elif task['response_type'] == 'text':
                text_response = request.form.get('text').strip()
                if not text_response:
                    flash('Введите ответ.')
                    return redirect(url_for('view_day', day=day))
                
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO submissions_day (user_id, day, file_url, text_response, submitted_at, status)
                VALUES (%s, %s, %s, %s, NOW(), 'pending')
            ''', (user_id, day, file_url, text_response))
            conn.commit()
            flash('Ответ отправлен на проверку.')
        except Exception as e:
            flash('Ошибка при отправке.')
            print(e)
        finally:
            conn.close()

        return redirect(url_for('view_day', day=day))

    return render_template('day.html', task=task, day=day, submission=submission)


@app.route('/admin/submissions')
def admin_submissions():
    if not session.get('is_admin'): 
        return redirect(url_for('login'))
    
    submissions = []
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.id, s.user_id, s.day, s.file_url, s.text_response, s.submitted_at, s.status,
                   u.username, t.title, t.points_free, t.points_global, t.is_paid
            FROM submissions_day s
            JOIN users u ON s.user_id = u.id
            JOIN tasks t ON s.day = t.day
            ORDER BY s.submitted_at DESC
        ''')
        submissions = cursor.fetchall()
    finally:
        conn.close()
    
    return render_template('admin_submissions.html', submissions=submissions)

@app.route('/admin/approve/day/<int:sub_id>')
def approve_day_submission(sub_id):
    if not session.get('is_admin'): return redirect(url_for('login'))
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.id, s.user_id, s.day, t.points_free, t.points_global, t.is_paid
            FROM submissions_day s
            JOIN tasks t ON s.day = t.day
            WHERE s.id = %s AND s.status = 'pending'
        ''', (sub_id,))
        sub = cursor.fetchone()
        if not sub:
            flash('Задание уже обработано.')
            return redirect(url_for('admin_submissions'))

        cursor.execute('UPDATE submissions_day SET status = %s WHERE id = %s', ('approved', sub_id))
        conn.commit()

        if sub['is_paid']:
            add_points(sub['user_id'], 0, sub['points_free'])
            flash(f'✅ +{sub["points_free"]} платных, +{sub["points_global"]} общих.')
        else:
            add_points(sub['user_id'], sub['points_free'], 0)
            flash(f'✅ +{sub["points_free"]} личных, +{sub["points_global"]} общих.')

        add_to_global_points(sub['points_global'])
        mark_day_as_opened(sub['user_id'], sub['day'])
        return redirect(url_for('admin_submissions'))

    except Exception as e:
        flash(f'❌ Ошибка: {str(e)}')
        return redirect(url_for('admin_submissions'))
    finally:
        conn.close()

@app.route('/admin')
def admin():
    if not session.get('is_admin'):
        flash('Доступ запрещён.')
        return redirect(url_for('login'))

    users = []
    stats = {}
    user_points = {}

    conn = get_db()
    try:
        cursor = conn.cursor()

        # Получаем всех пользователей
        cursor.execute('SELECT id, username FROM users ORDER BY username')
        users = cursor.fetchall()

        # Статистика: сколько дней открыл каждый
        cursor.execute('''
            SELECT u.username, COUNT(p.day) as total_opened
            FROM users u
            LEFT JOIN progress p ON u.id = p.user_id AND p.is_completed = 1
            GROUP BY u.id, u.username
        ''')
        for row in cursor.fetchall():
            stats[row['username']] = {'total_opened': row['total_opened']}

        # Личные баллы
        for user in users:
            free, paid = get_user_points(user['id'])
            user_points[user['username']] = free + paid

    finally:
        conn.close()

    # Получаем актуальные цели призов
    reward_targets = get_reward_targets()
    global_points = get_global_points()

    return render_template(
        'admin.html',
        users=users,
        stats=stats,
        user_points=user_points,
        global_points=global_points,
        reward_targets=reward_targets  # ← передаём в шаблон
    )

@app.route('/admin/add_global', methods=['POST'])
def add_global():
    if not session.get('is_admin'): return redirect(url_for('login'))
    points = int(request.form['points'])
    add_to_global_points(points)
    flash(f'+{points} к общему счёту')
    return redirect(url_for('admin'))

@app.route('/admin/add_user_points', methods=['POST'])
def add_user_points():
    if not session.get('is_admin'): return redirect(url_for('login'))
    user_id = int(request.form['user_id'])
    points = int(request.form['points'])
    add_points(user_id, points, 0)
    flash(f'+{points} пользователю')
    return redirect(url_for('admin'))

@app.route('/admin/remove_global', methods=['POST'])
def remove_global():
    if not session.get('is_admin'): return redirect(url_for('login'))
    points = int(request.form['points'])
    current = get_global_points()
    if points > current:
        flash(f'❌ Нельзя снять {points} (всего: {current})')
    else:
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('UPDATE global_progress SET total_points = %s WHERE id = 1', (max(0, current - points),))
            conn.commit()
            flash(f'✅ Снято {points} из общего счёта')
        finally:
            conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/remove_user_points', methods=['POST'])
def remove_user_points():
    if not session.get('is_admin'): return redirect(url_for('login'))
    user_id = int(request.form['user_id'])
    points = int(request.form['points'])
    free, paid = get_user_points(user_id)
    total = free + paid
    if points > total: flash(f'❌ Нельзя снять {points} (у пользователя: {total})')
    else: 
        # Просто уменьшаем общие (можно уточнить, откуда снимать)
        add_points(user_id, -points, 0)
        flash(f'✅ Снято {points}')
    return redirect(url_for('admin'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed = generate_password_hash(password)
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO users (username, password) VALUES (%s, %s)', (username, hashed))
            conn.commit()
            flash('Регистрация успешна!')
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:  # PostgreSQL
            flash('Имя занято.')
        except sqlite3.IntegrityError:  # SQLite (локально)
            flash('Имя занято.')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT id, username, password, is_admin FROM users WHERE username = %s', (username,))
            user = cursor.fetchone()
            if user and check_password_hash(user['password'], password):
                session.update(user_id=user['id'], username=user['username'], is_admin=bool(user['is_admin']))
                return redirect(url_for('calendar'))
            flash('Ошибка входа.')
        finally:
            conn.close()
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

try:
    init_db()
    print("✅ init_db() успешно выполнен")
except Exception as e:
    print(f"❌ Ошибка при инициализации БД: {e}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))





