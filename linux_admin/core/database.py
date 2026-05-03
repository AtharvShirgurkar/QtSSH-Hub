import os
import sqlite3

class DatabaseManager:
    def __init__(self):
        self.db_path = os.path.expanduser("~/.linux_admin_app/app.db")
        # In-memory runtime state for device reachability
        self.device_status = {} 

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    port INTEGER DEFAULT 22,
                    username TEXT NOT NULL,
                    auth_type TEXT NOT NULL,
                    credential TEXT NOT NULL,
                    group_id INTEGER,
                    FOREIGN KEY (group_id) REFERENCES groups(id)
                )
            ''')
            conn.commit()

    def add_group(self, name):
        with self.get_connection() as conn:
            conn.execute('INSERT INTO groups (name) VALUES (?)', (name,))
            conn.commit()

    def get_groups(self):
        with self.get_connection() as conn:
            cursor = conn.execute('SELECT id, name FROM groups')
            return [{"id": row[0], "name": row[1]} for row in cursor.fetchall()]

    def add_device(self, name, ip, port, username, auth_type, credential, group_id=None):
        with self.get_connection() as conn:
            conn.execute('''
                INSERT INTO devices (name, ip, port, username, auth_type, credential, group_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (name, ip, port, username, auth_type, credential, group_id))
            conn.commit()

    def get_devices(self, group_id=None):
        with self.get_connection() as conn:
            query = '''
                SELECT d.id, d.name, d.ip, d.port, d.username, d.auth_type, d.credential, g.name, d.group_id 
                FROM devices d LEFT JOIN groups g ON d.group_id = g.id
            '''
            params = ()
            if group_id:
                query += ' WHERE d.group_id = ?'
                params = (group_id,)
            cursor = conn.execute(query, params)
            return [{
                "id": row[0], "name": row[1], "ip": row[2], "port": row[3],
                "username": row[4], "auth_type": row[5], "credential": row[6], "group": row[7], "group_id": row[8]
            } for row in cursor.fetchall()]

    def delete_device(self, device_id):
        with self.get_connection() as conn:
            conn.execute('DELETE FROM devices WHERE id = ?', (device_id,))
            conn.commit()
            if device_id in self.device_status:
                del self.device_status[device_id]

    def update_device(self, device_id, name, ip, port, username, auth_type, credential, group_id):
        with self.get_connection() as conn:
            conn.execute('''
                UPDATE devices
                SET name = ?, ip = ?, port = ?, username = ?, auth_type = ?, credential = ?, group_id = ?
                WHERE id = ?
            ''', (name, ip, port, username, auth_type, credential, group_id, device_id))
            conn.commit()

    def delete_group(self, group_id):
        with self.get_connection() as conn:
            conn.execute('UPDATE devices SET group_id = NULL WHERE group_id = ?', (group_id,))
            conn.execute('DELETE FROM groups WHERE id = ?', (group_id,))
            conn.commit()
