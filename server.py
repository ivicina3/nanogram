import json
import os
import sqlite3
import socketserver
import threading
import hashlib
import binascii

DB_PATH = os.path.join(os.path.dirname(__file__), "chat.db")
SALT = b"nanogram_salt_v1"

class ChatDatabase:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    owner_id INTEGER NOT NULL,
                    FOREIGN KEY(owner_id) REFERENCES users(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS group_members (
                    group_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    UNIQUE(group_id, user_id),
                    FOREIGN KEY(group_id) REFERENCES groups(id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            conn.commit()

    def _hash_password(self, password: str) -> str:
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), SALT, 100_000)
        return binascii.hexlify(dk).decode("ascii")

    def register_user(self, username: str, password: str) -> bool:
        password_hash = self._hash_password(password)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, password_hash),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def authenticate_user(self, username: str, password: str) -> bool:
        password_hash = self._hash_password(password)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT password_hash FROM users WHERE username = ?",
                (username,),
            )
            row = cursor.fetchone()
            return bool(row and row[0] == password_hash)

    def get_user_id(self, username: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            return row[0] if row else None

    def create_group(self, name: str, owner_username: str, members: list[str]) -> tuple[bool, str]:
        owner_id = self.get_user_id(owner_username)
        if owner_id is None:
            return False, "Owner does not exist"
        if self.get_group_id(name) is not None:
            return False, "Group already exists"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO groups (name, owner_id) VALUES (?, ?)",
                (name, owner_id),
            )
            group_id = cursor.lastrowid
            members = list(dict.fromkeys(members + [owner_username]))
            for member_username in members:
                member_id = self.get_user_id(member_username)
                if member_id is None:
                    conn.rollback()
                    return False, f"User '{member_username}' does not exist"
                cursor.execute(
                    "INSERT INTO group_members (group_id, user_id) VALUES (?, ?)",
                    (group_id, member_id),
                )
            conn.commit()
        return True, "Group created"

    def get_group_id(self, name: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM groups WHERE name = ?", (name,))
            row = cursor.fetchone()
            return row[0] if row else None

    def get_group_members(self, group_name: str) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT u.username FROM users u JOIN group_members gm ON u.id = gm.user_id JOIN groups g ON g.id = gm.group_id WHERE g.name = ?",
                (group_name,),
            )
            return [row[0] for row in cursor.fetchall()]

    def list_users(self) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users ORDER BY username")
            return [row[0] for row in cursor.fetchall()]

    def list_groups(self) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM groups ORDER BY name")
            return [row[0] for row in cursor.fetchall()]


class ThreadedTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


class ChatHandler(socketserver.StreamRequestHandler):
    active_clients = {}
    active_lock = threading.Lock()
    db = ChatDatabase()

    def handle(self):
        self.username = None
        self.request.settimeout(600)
        self.wfile.write(b"{" + b'"status":"ok","message":"Welcome to Nanogram chat server"}' + b"\n")
        for raw_line in self.rfile:
            try:
                line = raw_line.strip().decode("utf-8")
            except UnicodeDecodeError:
                continue
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                self.send_response(False, "Invalid JSON")
                continue
            self.process_request(data)
        self.logout()

    def finish(self):
        self.logout()
        super().finish()

    def process_request(self, data: dict):
        action = data.get("action")
        if action == "register":
            self.action_register(data)
        elif action == "login":
            self.action_login(data)
        elif action == "private":
            self.action_private(data)
        elif action == "create_group":
            self.action_create_group(data)
        elif action == "group":
            self.action_group(data)
        elif action == "list_users":
            self.action_list_users()
        elif action == "list_groups":
            self.action_list_groups()
        else:
            self.send_response(False, "Unknown action")

    def send_response(self, success: bool, message: str, payload: dict | None = None):
        payload = payload or {}
        response = {"status": "ok" if success else "error", "message": message, **payload}
        self.wfile.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))

    def action_register(self, data: dict):
        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            self.send_response(False, "Require username and password")
            return
        if self.db.register_user(username, password):
            self.send_response(True, "Registered successfully")
        else:
            self.send_response(False, "Username already taken")

    def action_login(self, data: dict):
        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            self.send_response(False, "Require username and password")
            return
        if self.db.authenticate_user(username, password):
            with self.active_lock:
                if username in self.active_clients:
                    self.send_response(False, "User already logged in")
                    return
                self.active_clients[username] = self
            self.username = username
            self.send_response(True, f"Logged in as {username}")
        else:
            self.send_response(False, "Invalid username or password")

    def action_private(self, data: dict):
        if not self.username:
            self.send_response(False, "Login first")
            return
        recipient = data.get("to")
        message = data.get("message")
        if not recipient or not message:
            self.send_response(False, "Private message requires recipient and message")
            return
        with self.active_lock:
            target = self.active_clients.get(recipient)
        if target:
            target.send_response(True, f"Private from {self.username}: {message}", {"type": "private", "from": self.username, "message": message})
            self.send_response(True, "Message sent")
        else:
            self.send_response(False, f"User '{recipient}' is offline or does not exist")

    def action_create_group(self, data: dict):
        if not self.username:
            self.send_response(False, "Login first")
            return
        name = data.get("group")
        members = data.get("members")
        if not name or not isinstance(members, list) or not members:
            self.send_response(False, "Group creation requires group name and member list")
            return
        success, message = self.db.create_group(name, self.username, members)
        self.send_response(success, message)

    def action_group(self, data: dict):
        if not self.username:
            self.send_response(False, "Login first")
            return
        group_name = data.get("group")
        message = data.get("message")
        if not group_name or not message:
            self.send_response(False, "Group message requires group name and message")
            return
        members = self.db.get_group_members(group_name)
        if self.username not in members:
            self.send_response(False, "You are not a member of this group")
            return
        if len(members) <= 1:
            self.send_response(False, "Group has no other members online")
            return
        sent_count = 0
        with self.active_lock:
            for member in members:
                if member == self.username:
                    continue
                target = self.active_clients.get(member)
                if target:
                    target.send_response(True, f"Group {group_name} from {self.username}: {message}", {"type": "group", "group": group_name, "from": self.username, "message": message})
                    sent_count += 1
        self.send_response(True, f"Group message sent to {sent_count} active members")

    def action_list_users(self):
        users = self.db.list_users()
        self.send_response(True, "User list", {"users": users})

    def action_list_groups(self):
        groups = self.db.list_groups()
        self.send_response(True, "Group list", {"groups": groups})

    def logout(self):
        if self.username:
            with self.active_lock:
                if self.active_clients.get(self.username) is self:
                    del self.active_clients[self.username]
            self.username = None


if __name__ == "__main__":
    host = "0.0.0.0"
    port = 12345
    print(f"Starting server on {host}:{port}")
    with ThreadedTCPServer((host, port), ChatHandler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Shutting down server")
            server.shutdown()
