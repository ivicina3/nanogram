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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    msg_type TEXT NOT NULL CHECK(msg_type IN ('private', 'group')),
                    sender_id INTEGER NOT NULL,
                    recipient_id INTEGER,
                    group_id INTEGER,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(sender_id) REFERENCES users(id),
                    FOREIGN KEY(recipient_id) REFERENCES users(id),
                    FOREIGN KEY(group_id) REFERENCES groups(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipient_id INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    delivered INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(recipient_id) REFERENCES users(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_avatars (
                    user_id INTEGER PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    image_b64 TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
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

    def get_username_by_id(self, user_id: int):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
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

    def save_private_message(self, sender_username: str, recipient_username: str, message: str) -> tuple[bool, str]:
        sender_id = self.get_user_id(sender_username)
        recipient_id = self.get_user_id(recipient_username)
        if sender_id is None or recipient_id is None:
            return False, "Sender or recipient does not exist"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO messages (msg_type, sender_id, recipient_id, content)
                VALUES ('private', ?, ?, ?)
                """,
                (sender_id, recipient_id, message),
            )
            conn.commit()
        return True, "Message stored"

    def save_group_message(self, sender_username: str, group_name: str, message: str) -> tuple[bool, str]:
        sender_id = self.get_user_id(sender_username)
        group_id = self.get_group_id(group_name)
        if sender_id is None or group_id is None:
            return False, "Sender or group does not exist"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO messages (msg_type, sender_id, group_id, content)
                VALUES ('group', ?, ?, ?)
                """,
                (sender_id, group_id, message),
            )
            conn.commit()
        return True, "Message stored"

    def get_private_history(self, username: str, peer_username: str, limit: int = 50) -> tuple[bool, str, list[dict]]:
        user_id = self.get_user_id(username)
        peer_id = self.get_user_id(peer_username)
        if user_id is None or peer_id is None:
            return False, "User does not exist", []
        safe_limit = max(1, min(limit, 200))
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT m.sender_id, m.content, m.created_at
                FROM messages m
                WHERE m.msg_type = 'private'
                  AND ((m.sender_id = ? AND m.recipient_id = ?)
                       OR (m.sender_id = ? AND m.recipient_id = ?))
                ORDER BY m.id DESC
                LIMIT ?
                """,
                (user_id, peer_id, peer_id, user_id, safe_limit),
            )
            rows = cursor.fetchall()
        rows.reverse()
        items = []
        for sender_id, content, created_at in rows:
            sender_name = self.get_username_by_id(sender_id) or "unknown"
            items.append({"from": sender_name, "message": content, "created_at": created_at})
        return True, "Private history", items

    def get_group_history(self, username: str, group_name: str, limit: int = 50) -> tuple[bool, str, list[dict]]:
        members = self.get_group_members(group_name)
        if username not in members:
            return False, "You are not a member of this group", []
        group_id = self.get_group_id(group_name)
        if group_id is None:
            return False, "Group does not exist", []
        safe_limit = max(1, min(limit, 200))
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT m.sender_id, m.content, m.created_at
                FROM messages m
                WHERE m.msg_type = 'group' AND m.group_id = ?
                ORDER BY m.id DESC
                LIMIT ?
                """,
                (group_id, safe_limit),
            )
            rows = cursor.fetchall()
        rows.reverse()
        items = []
        for sender_id, content, created_at in rows:
            sender_name = self.get_username_by_id(sender_id) or "unknown"
            items.append({"from": sender_name, "message": content, "created_at": created_at})
        return True, "Group history", items

    def enqueue_pending_message(self, recipient_username: str, payload: dict) -> tuple[bool, str]:
        recipient_id = self.get_user_id(recipient_username)
        if recipient_id is None:
            return False, "Recipient does not exist"
        serialized = json.dumps(payload, ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO pending_messages (recipient_id, payload, delivered) VALUES (?, ?, 0)",
                (recipient_id, serialized),
            )
            conn.commit()
        return True, "Queued for delivery"

    def get_pending_messages(self, recipient_username: str, limit: int = 500) -> tuple[bool, str, list[tuple[int, dict]]]:
        recipient_id = self.get_user_id(recipient_username)
        if recipient_id is None:
            return False, "Recipient does not exist", []
        safe_limit = max(1, min(limit, 5000))
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, payload
                FROM pending_messages
                WHERE recipient_id = ? AND delivered = 0
                ORDER BY id ASC
                LIMIT ?
                """,
                (recipient_id, safe_limit),
            )
            rows = cursor.fetchall()
        items = []
        for row_id, payload_json in rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                payload = {"type": "system", "message": "Corrupted pending payload"}
            items.append((row_id, payload))
        return True, "Pending messages", items

    def mark_pending_delivered(self, ids: list[int]):
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE pending_messages SET delivered = 1 WHERE id IN ({placeholders})", ids)
            conn.commit()

    def set_user_avatar(self, username: str, file_name: str, image_b64: str) -> tuple[bool, str]:
        user_id = self.get_user_id(username)
        if user_id is None:
            return False, "User does not exist"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO user_avatars (user_id, file_name, image_b64, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    file_name=excluded.file_name,
                    image_b64=excluded.image_b64,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, file_name, image_b64),
            )
            conn.commit()
        return True, "Avatar saved"

    def get_user_avatar(self, username: str) -> tuple[bool, str, dict]:
        user_id = self.get_user_id(username)
        if user_id is None:
            return False, "User does not exist", {}
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_name, image_b64 FROM user_avatars WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
        if not row:
            return True, "Avatar not set", {}
        return True, "Avatar loaded", {"avatar_name": row[0], "avatar_data": row[1]}


class ThreadedTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ChatHandler(socketserver.StreamRequestHandler):
    active_clients = {}
    active_lock = threading.Lock()
    db = ChatDatabase()

    def handle(self):
        self.username = None
        self.write_lock = threading.Lock()
        self.request.settimeout(600)
        self._write_json({"status": "ok", "message": "Welcome to Nanogram chat server"})
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
            try:
                self.process_request(data)
            except Exception as exc:
                self.send_response(False, f"Server error: {exc}")
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
        elif action == "history_private":
            self.action_history_private(data)
        elif action == "history_group":
            self.action_history_group(data)
        elif action == "set_avatar":
            self.action_set_avatar(data)
        elif action == "get_avatar":
            self.action_get_avatar(data)
        else:
            self.send_response(False, "Unknown action")

    def send_response(self, success: bool, message: str, payload: dict | None = None):
        payload = payload or {}
        response = {"status": "ok" if success else "error", "message": message, **payload}
        return self._write_json(response)

    def _write_json(self, payload: dict) -> bool:
        try:
            with self.write_lock:
                self.wfile.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
            return True
        except OSError:
            return False

    def _deliver_payload_to_online_user(self, username: str, payload: dict) -> bool:
        with self.active_lock:
            target = self.active_clients.get(username)
        if not target:
            return False
        sent = target.send_response(True, payload.get("message", "Message"), payload)
        if sent:
            return True
        with self.active_lock:
            if self.active_clients.get(username) is target:
                del self.active_clients[username]
        return False

    def _queue_payload(self, recipient: str, payload: dict) -> bool:
        ok, _msg = self.db.enqueue_pending_message(recipient, payload)
        return ok

    def _sender_avatar_payload(self, sender_username: str) -> dict:
        ok, _msg, avatar = self.db.get_user_avatar(sender_username)
        if ok and avatar:
            return avatar
        return {}

    def _deliver_pending_messages(self):
        if not self.username:
            return
        ok, _msg, items = self.db.get_pending_messages(self.username)
        if not ok or not items:
            return
        delivered_ids = []
        for pending_id, payload in items:
            sent = self.send_response(True, payload.get("message", "Pending message"), payload)
            if not sent:
                break
            delivered_ids.append(pending_id)
        self.db.mark_pending_delivered(delivered_ids)
        if delivered_ids:
            self.send_response(True, f"Delivered {len(delivered_ids)} pending messages")

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
            self._deliver_pending_messages()
        else:
            self.send_response(False, "Invalid username or password")

    def action_private(self, data: dict):
        if not self.username:
            self.send_response(False, "Login first")
            return
        recipient = data.get("to")
        message = (data.get("message") or "").strip()
        image_name = data.get("image_name")
        image_data = data.get("image_data")
        has_image = bool(image_name and image_data)
        if not recipient or (not message and not has_image):
            self.send_response(False, "Private message requires recipient and text or image")
            return
        if message:
            ok, db_message = self.db.save_private_message(self.username, recipient, message)
            if not ok:
                self.send_response(False, db_message)
                return
        payload = {"type": "private", "from": self.username, "message": message}
        payload.update(self._sender_avatar_payload(self.username))
        if has_image:
            payload["image_name"] = image_name
            payload["image_data"] = image_data
        if self._deliver_payload_to_online_user(recipient, payload):
            self.send_response(True, "Message sent", {"delivered": True})
        else:
            if self._queue_payload(recipient, payload):
                self.send_response(True, f"User '{recipient}' is offline. Message queued until online", {"delivered": False, "queued": True})
            else:
                self.send_response(False, f"Cannot deliver or queue for '{recipient}'")

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
        message = (data.get("message") or "").strip()
        image_name = data.get("image_name")
        image_data = data.get("image_data")
        has_image = bool(image_name and image_data)
        if not group_name or (not message and not has_image):
            self.send_response(False, "Group message requires group name and text or image")
            return
        members = self.db.get_group_members(group_name)
        if self.username not in members:
            self.send_response(False, "You are not a member of this group")
            return
        if len(members) <= 1:
            pass
        if message:
            ok, db_message = self.db.save_group_message(self.username, group_name, message)
            if not ok:
                self.send_response(False, db_message)
                return
        sent_count = 0
        queued_count = 0
        payload = {"type": "group", "group": group_name, "from": self.username, "message": message}
        payload.update(self._sender_avatar_payload(self.username))
        if has_image:
            payload["image_name"] = image_name
            payload["image_data"] = image_data
        for member in members:
            if member == self.username:
                continue
            if self._deliver_payload_to_online_user(member, payload):
                sent_count += 1
            elif self._queue_payload(member, payload):
                queued_count += 1
        self.send_response(True, f"Group message sent to {sent_count} online members, queued for {queued_count} offline members")

    def action_list_users(self):
        users = self.db.list_users()
        self.send_response(True, "User list", {"users": users})

    def action_list_groups(self):
        groups = self.db.list_groups()
        self.send_response(True, "Group list", {"groups": groups})

    def action_history_private(self, data: dict):
        if not self.username:
            self.send_response(False, "Login first")
            return
        peer = data.get("with")
        if not peer:
            self.send_response(False, "Private history requires a username")
            return
        limit = data.get("limit", 50)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            self.send_response(False, "Limit must be a number")
            return
        ok, message, items = self.db.get_private_history(self.username, peer, limit)
        if not ok:
            self.send_response(False, message)
            return
        self.send_response(True, message, {"type": "history_private", "with": peer, "messages": items})

    def action_history_group(self, data: dict):
        if not self.username:
            self.send_response(False, "Login first")
            return
        group_name = data.get("group")
        if not group_name:
            self.send_response(False, "Group history requires group name")
            return
        limit = data.get("limit", 50)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            self.send_response(False, "Limit must be a number")
            return
        ok, message, items = self.db.get_group_history(self.username, group_name, limit)
        if not ok:
            self.send_response(False, message)
            return
        self.send_response(True, message, {"type": "history_group", "group": group_name, "messages": items})

    def action_set_avatar(self, data: dict):
        if not self.username:
            self.send_response(False, "Login first")
            return
        avatar_name = data.get("avatar_name")
        avatar_data = data.get("avatar_data")
        if not avatar_name or not avatar_data:
            self.send_response(False, "Avatar name and data required")
            return
        ok, message = self.db.set_user_avatar(self.username, avatar_name, avatar_data)
        self.send_response(ok, message)

    def action_get_avatar(self, data: dict):
        if not self.username:
            self.send_response(False, "Login first")
            return
        target_user = data.get("username") or self.username
        ok, message, avatar = self.db.get_user_avatar(target_user)
        payload = {"type": "avatar", "username": target_user}
        payload.update(avatar)
        self.send_response(ok, message, payload)

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
