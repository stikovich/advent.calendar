import sqlite3
with sqlite3.connect('database.db') as conn:
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)', 
                   ('admin', '22551bdg'))  # Пароль в открытом виде — временно!
    conn.commit()
