import sqlite3
import os

DB_PATH = "groups_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fb_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            name TEXT,
            status TEXT DEFAULT 'unknown',
            last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_groups(groups: list):
    """
    Lưu danh sách groups (url, name) vào DB. Cập nhật nếu đã có.
    """
    if not groups:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for g in groups:
        # Sử dụng UPSERT (ON CONFLICT DO UPDATE) 
        cursor.execute('''
            INSERT INTO fb_groups (url, name)
            VALUES (?, ?)
            ON CONFLICT(url) DO UPDATE SET 
                name=excluded.name, 
                last_scanned=CURRENT_TIMESTAMP
        ''', (g.get('url'), g.get('name', '')))
    conn.commit()
    conn.close()

def get_all_groups():
    """Trích xuất tất cả các group từ DB"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT url, name, status, last_scanned FROM fb_groups ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for r in rows:
        result.append({
            'url': r[0],
            'name': r[1],
            'status': r[2],
            'last_scanned': r[3]
        })
    return result

def count_groups():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM fb_groups')
    count = cursor.fetchone()[0]
    conn.close()
    return count

init_db()
