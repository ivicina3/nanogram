import base64
import json
import os
import shutil
import socket
import threading
import traceback
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from PIL import Image
from tkinter import filedialog, messagebox

DEFAULT_SERVER_HOST = "195.208.118.78"
DEFAULT_SERVER_PORT = 12345
CHAT_REFRESH_MS = 15000
THUMB_SIZE = (240, 240)
AVATAR_SIZE = (36, 36)


class NanogramGUI:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.geometry("1200x760")
        self.root.title("Nanogram Desktop")

        self.sock = None
        self.username = None
        self.listener_thread = None
        self.listener_running = False
        self.receive_buffer = ""

        self.current_chat_type = None
        self.current_chat_name = None
        self.chat_items = []
        self.search_var = ctk.StringVar()
        self.chat_map = {}
        self.image_refs = []

        self.local_cache = {"chats": {}, "avatars": {}}

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.create_widgets()
        self.auto_connect()
        self.root.after(CHAT_REFRESH_MS, self.periodic_refresh)

    def create_widgets(self):
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        # Top auth bar only (without connect/disconnect buttons)
        top = ctk.CTkFrame(self.root, corner_radius=0)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
        top.grid_columnconfigure(7, weight=1)

        self.user_entry = ctk.CTkEntry(top, placeholder_text="Username", width=180)
        self.user_entry.grid(row=0, column=0, padx=8, pady=8)
        self.pass_entry = ctk.CTkEntry(top, placeholder_text="Password", show="*", width=180)
        self.pass_entry.grid(row=0, column=1, padx=8, pady=8)
        self.register_btn = ctk.CTkButton(top, text="Register", width=110, command=self.register)
        self.register_btn.grid(row=0, column=2, padx=6, pady=8)
        self.login_btn = ctk.CTkButton(top, text="Login", width=90, command=self.login)
        self.login_btn.grid(row=0, column=3, padx=6, pady=8)
        self.avatar_btn = ctk.CTkButton(top, text="Avatar", width=90, command=self.choose_avatar)
        self.avatar_btn.grid(row=0, column=4, padx=6, pady=8)
        self.status_label = ctk.CTkLabel(top, text="Connecting...")
        self.status_label.grid(row=0, column=7, padx=8, pady=8, sticky="e")

        # Left sidebar (search + chats list)
        left = ctk.CTkFrame(self.root, width=300)
        left.grid(row=1, column=0, sticky="nsw", padx=(8, 4), pady=8)
        left.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(left, text="Chats", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, padx=12, pady=(12, 8), sticky="w")
        self.search_entry = ctk.CTkEntry(left, textvariable=self.search_var, placeholder_text="Search chat")
        self.search_entry.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        self.search_var.trace_add("write", lambda *_: self.refresh_chat_listbox())

        self.chat_listbox = ctk.CTkTextbox(left, width=280, wrap="none", state="disabled")
        self.chat_listbox.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.chat_listbox.bind("<Button-1>", self.on_chat_click)

        # Right panel
        right = ctk.CTkFrame(self.root)
        right.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=8)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self.chat_header = ctk.CTkLabel(right, text="Select chat", anchor="w", font=ctk.CTkFont(size=18, weight="bold"))
        self.chat_header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 8))

        self.messages_frame = ctk.CTkScrollableFrame(right)
        self.messages_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.messages_frame.grid_columnconfigure(0, weight=1)

        compose = ctk.CTkFrame(right)
        compose.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        compose.grid_columnconfigure(0, weight=1)

        self.message_entry = ctk.CTkEntry(compose, placeholder_text="Write a message")
        self.message_entry.grid(row=0, column=0, sticky="ew", padx=(8, 6), pady=8)
        self.message_entry.bind("<Return>", lambda _e: self.send_current_message())
        self.photo_btn = ctk.CTkButton(compose, text="Photo", width=90, command=self.send_photo)
        self.photo_btn.grid(row=0, column=1, padx=6, pady=8)
        self.send_btn = ctk.CTkButton(compose, text="Send", width=90, command=self.send_current_message)
        self.send_btn.grid(row=0, column=2, padx=(0, 8), pady=8)

    # -------------------- Local storage --------------------
    def _safe_name(self, value: str) -> str:
        return "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_", ".")).strip("._") or "user"

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _data_root(self) -> Path:
        root = Path(__file__).resolve().parent / "client_data"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _active_user(self) -> str:
        return self._safe_name(self.username) if self.username else "guest"

    def _user_root(self) -> Path:
        root = self._data_root() / self._active_user()
        (root / "media").mkdir(parents=True, exist_ok=True)
        (root / "avatars").mkdir(parents=True, exist_ok=True)
        return root

    def _messages_path(self) -> Path:
        return self._user_root() / "messages.json"

    def _save_local_cache(self):
        self._messages_path().write_text(json.dumps(self.local_cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_local_cache(self):
        self.local_cache = {"chats": {}, "avatars": {}}
        path = self._messages_path()
        if path.exists():
            try:
                self.local_cache = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                self.local_cache = {"chats": {}, "avatars": {}}
        self.chat_items.clear()
        self.chat_map.clear()
        for key in self.local_cache.get("chats", {}):
            if ":" not in key:
                continue
            chat_type, chat_name = key.split(":", 1)
            if chat_type in ("private", "group"):
                self.chat_items.append((chat_type, chat_name))
        self.refresh_chat_listbox()

    def _chat_key(self, chat_type: str, chat_name: str) -> str:
        return f"{chat_type}:{chat_name}"

    def _append_local_entry(self, chat_type: str, chat_name: str, entry: dict):
        key = self._chat_key(chat_type, chat_name)
        chats = self.local_cache.setdefault("chats", {})
        chats.setdefault(key, []).append(entry)
        self.add_chat_item(chat_type, chat_name)
        self._save_local_cache()

    # -------------------- Rendering --------------------
    def add_chat_item(self, chat_type: str, chat_name: str):
        if (chat_type, chat_name) not in self.chat_items:
            self.chat_items.append((chat_type, chat_name))
            self.refresh_chat_listbox()

    def refresh_chat_listbox(self):
        filter_text = self.search_var.get().strip().lower()
        self.chat_map.clear()
        lines = []
        idx = 0
        for chat_type, chat_name in sorted(self.chat_items, key=lambda t: (t[0], t[1].lower())):
            if filter_text and filter_text not in chat_name.lower():
                continue
            line = f"@ {chat_name}" if chat_type == "private" else f"# {chat_name}"
            lines.append(line)
            self.chat_map[idx] = (chat_type, chat_name)
            idx += 1
        self.chat_listbox.configure(state="normal")
        self.chat_listbox.delete("1.0", "end")
        self.chat_listbox.insert("1.0", "\n".join(lines))
        self.chat_listbox.configure(state="disabled")

    def on_chat_click(self, event):
        try:
            index = self.chat_listbox.index(f"@{event.x},{event.y}")
            line_no = int(index.split(".")[0]) - 1
            if line_no in self.chat_map:
                chat_type, chat_name = self.chat_map[line_no]
                self.select_chat(chat_type, chat_name)
        except Exception:
            return

    def select_chat(self, chat_type: str, chat_name: str):
        self.current_chat_type = chat_type
        self.current_chat_name = chat_name
        self.chat_header.configure(text=(f"Chat: {chat_name}" if chat_type == "private" else f"Group: {chat_name}"))
        if chat_type == "private":
            self.send_message({"action": "get_avatar", "username": chat_name})
        if self.username:
            self.send_message({"action": "get_avatar", "username": self.username})
        self._render_local_chat()

    def _clear_messages_ui(self):
        for child in self.messages_frame.winfo_children():
            child.destroy()
        self.image_refs.clear()

    def _avatar_path(self, username: str) -> str | None:
        return self.local_cache.get("avatars", {}).get(username)

    def _save_server_avatar(self, username: str, avatar_name: str, avatar_data_b64: str) -> str | None:
        try:
            raw = base64.b64decode(avatar_data_b64.encode("ascii"))
            target = self._user_root() / "avatars" / f"server_{self._safe_name(username)}_{self._safe_name(avatar_name)}"
            target.write_bytes(raw)
            self.local_cache.setdefault("avatars", {})[username] = str(target)
            self._save_local_cache()
            return str(target)
        except Exception:
            return None

    def _render_bubble(self, entry: dict):
        mine = bool(entry.get("mine"))
        sender = entry.get("from", "unknown")
        text = entry.get("text", "")
        ts = entry.get("ts", "")
        kind = entry.get("kind", "text")
        image_path = entry.get("file")

        row = ctk.CTkFrame(self.messages_frame, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=4)
        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=1)

        bubble_col = 1 if mine else 0
        bubble = ctk.CTkFrame(row, fg_color=("#2F5D8C" if mine else "#2A2D31"), corner_radius=14)
        bubble.grid(row=0, column=bubble_col, sticky=("e" if mine else "w"), padx=6)

        header_row = ctk.CTkFrame(bubble, fg_color="transparent")
        header_row.pack(fill="x", padx=10, pady=(8, 0))
        avatar_user = sender if not mine else (self.username or sender)
        avatar_path = self._avatar_path(avatar_user)
        if avatar_path and Path(avatar_path).exists():
            try:
                av = Image.open(avatar_path)
                av.thumbnail(AVATAR_SIZE)
                av_img = ctk.CTkImage(light_image=av, dark_image=av, size=av.size)
                self.image_refs.append(av_img)
                ctk.CTkLabel(header_row, text="", image=av_img, width=AVATAR_SIZE[0]).pack(side="left", padx=(0, 6))
            except Exception:
                pass
        header = sender if not mine else "You"
        ctk.CTkLabel(header_row, text=header, anchor="w", text_color="#BBD8FF").pack(side="left")

        if kind == "photo" and image_path and Path(image_path).exists():
            try:
                image = Image.open(image_path)
                image.thumbnail(THUMB_SIZE)
                ctk_img = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
                self.image_refs.append(ctk_img)
                img_label = ctk.CTkLabel(bubble, image=ctk_img, text="")
                img_label.pack(padx=10, pady=(6, 4))
                img_label.bind("<Button-1>", lambda _e, p=image_path: self.open_image(p))
            except Exception:
                ctk.CTkLabel(bubble, text=f"[photo] {Path(image_path).name}").pack(padx=10, pady=(6, 2))
        elif kind == "photo":
            ctk.CTkLabel(bubble, text="[photo]").pack(padx=10, pady=(6, 2))

        if text:
            ctk.CTkLabel(bubble, text=text, wraplength=420, justify="left").pack(padx=10, pady=(2, 2))
        ctk.CTkLabel(bubble, text=ts, text_color="#AEB4BC").pack(anchor="e", padx=10, pady=(0, 8))

    def _render_local_chat(self):
        self._clear_messages_ui()
        if not self.current_chat_name:
            return
        key = self._chat_key(self.current_chat_type, self.current_chat_name)
        entries = self.local_cache.get("chats", {}).get(key, [])
        for entry in entries:
            self._render_bubble(entry)

    # -------------------- Network --------------------
    def auto_connect(self):
        try:
            self.sock = socket.create_connection((DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT), timeout=10)
            self.sock.setblocking(True)
            self.listener_running = True
            self.status_label.configure(text=f"Connected {DEFAULT_SERVER_HOST}:{DEFAULT_SERVER_PORT}")
            self.listener_thread = threading.Thread(target=self.listen_server, daemon=True)
            self.listener_thread.start()
        except Exception as exc:
            self.status_label.configure(text=f"Offline ({exc})")

    def listen_server(self):
        try:
            while self.listener_running and self.sock:
                try:
                    data = self.sock.recv(8192)
                except OSError:
                    break
                if not data:
                    break
                self.receive_buffer += data.decode("utf-8", errors="replace")
                while "\n" in self.receive_buffer:
                    line, self.receive_buffer = self.receive_buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self.root.after(0, lambda p=payload: self.process_server_message(p))
        finally:
            self.root.after(0, lambda: self.status_label.configure(text="Disconnected"))

    def send_message(self, payload: dict) -> bool:
        if not self.sock:
            messagebox.showerror("Error", "Not connected to server")
            return False
        try:
            raw = json.dumps(payload, ensure_ascii=False) + "\n"
            self.sock.sendall(raw.encode("utf-8"))
            return True
        except Exception as exc:
            messagebox.showerror("Error", f"Send failed: {exc}")
            return False

    # -------------------- Actions --------------------
    def register(self):
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()
        if not username or not password:
            return
        self.send_message({"action": "register", "username": username, "password": password})

    def login(self):
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()
        if not username or not password:
            return
        self.username = username
        if self.send_message({"action": "login", "username": username, "password": password}):
            self._load_local_cache()
            self.list_users()
            self.list_groups()
            self.send_message({"action": "get_avatar", "username": self.username})

    def list_users(self):
        self.send_message({"action": "list_users"})

    def list_groups(self):
        self.send_message({"action": "list_groups"})

    def periodic_refresh(self):
        if self.username:
            self.list_users()
            self.list_groups()
        self.root.after(CHAT_REFRESH_MS, self.periodic_refresh)

    def send_current_message(self):
        text = self.message_entry.get().strip()
        if not text or not self.current_chat_name:
            return
        entry = {"kind": "text", "from": self.username or "me", "text": text, "ts": self._now(), "mine": True}
        if self.current_chat_type == "private":
            ok = self.send_message({"action": "private", "to": self.current_chat_name, "message": text})
            if ok:
                self._append_local_entry("private", self.current_chat_name, entry)
                self._render_local_chat()
        elif self.current_chat_type == "group":
            ok = self.send_message({"action": "group", "group": self.current_chat_name, "message": text})
            if ok:
                self._append_local_entry("group", self.current_chat_name, entry)
                self._render_local_chat()
        self.message_entry.delete(0, "end")

    def _save_incoming_photo(self, sender: str, image_name: str, image_data_b64: str) -> str | None:
        try:
            raw = base64.b64decode(image_data_b64.encode("ascii"))
            target = self._user_root() / "media" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._safe_name(sender)}_{self._safe_name(image_name)}"
            target.write_bytes(raw)
            return str(target)
        except Exception:
            return None

    def _copy_outgoing_photo(self, file_path: str) -> str | None:
        try:
            src = Path(file_path)
            target = self._user_root() / "media" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_me_{self._safe_name(src.name)}"
            shutil.copy2(src, target)
            return str(target)
        except Exception:
            return None

    def send_photo(self):
        if not self.current_chat_name:
            messagebox.showerror("Error", "Select chat first")
            return
        file_path = filedialog.askopenfilename(
            title="Select photo",
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp"), ("All files", "*.*")],
        )
        if not file_path:
            return
        try:
            image_raw = Path(file_path).read_bytes()
            image_data = base64.b64encode(image_raw).decode("ascii")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to read image: {exc}")
            return
        caption = self.message_entry.get().strip()
        payload = {"message": caption, "image_name": Path(file_path).name, "image_data": image_data}
        if self.current_chat_type == "private":
            payload.update({"action": "private", "to": self.current_chat_name})
            ok = self.send_message(payload)
            if ok:
                local_file = self._copy_outgoing_photo(file_path) or file_path
                self._append_local_entry("private", self.current_chat_name, {"kind": "photo", "from": self.username or "me", "text": caption, "file": local_file, "ts": self._now(), "mine": True})
                self._render_local_chat()
        elif self.current_chat_type == "group":
            payload.update({"action": "group", "group": self.current_chat_name})
            ok = self.send_message(payload)
            if ok:
                local_file = self._copy_outgoing_photo(file_path) or file_path
                self._append_local_entry("group", self.current_chat_name, {"kind": "photo", "from": self.username or "me", "text": caption, "file": local_file, "ts": self._now(), "mine": True})
                self._render_local_chat()
        self.message_entry.delete(0, "end")

    def choose_avatar(self):
        if not self.username:
            messagebox.showerror("Error", "Login first")
            return
        file_path = filedialog.askopenfilename(
            title="Choose avatar",
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp"), ("All files", "*.*")],
        )
        if not file_path:
            return
        src = Path(file_path)
        target = self._user_root() / "avatars" / f"avatar{src.suffix.lower() or '.png'}"
        shutil.copy2(src, target)
        try:
            avatar_data = base64.b64encode(src.read_bytes()).decode("ascii")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to read avatar: {exc}")
            return
        ok = self.send_message({"action": "set_avatar", "avatar_name": src.name, "avatar_data": avatar_data})
        if not ok:
            return
        self.local_cache.setdefault("avatars", {})[self.username] = str(target)
        self._save_local_cache()
        messagebox.showinfo("Avatar", "Avatar uploaded to server")

    def open_image(self, path: str):
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("Error", f"Cannot open image: {exc}")

    def process_server_message(self, data: dict):
        msg_type = data.get("type")
        if msg_type == "avatar":
            username = data.get("username")
            avatar_name = data.get("avatar_name")
            avatar_data = data.get("avatar_data")
            if username and avatar_name and avatar_data:
                self._save_server_avatar(username, avatar_name, avatar_data)
                if self.current_chat_name:
                    self._render_local_chat()
            return
        if "users" in data:
            for user in data.get("users", []):
                if user != self.username:
                    self.add_chat_item("private", user)
        if "groups" in data:
            for group in data.get("groups", []):
                self.add_chat_item("group", group)

        if msg_type == "private":
            from_user = data.get("from", "unknown")
            text = data.get("message", "")
            image_name = data.get("image_name")
            image_data = data.get("image_data")
            avatar_name = data.get("avatar_name")
            avatar_data = data.get("avatar_data")
            if avatar_name and avatar_data:
                self._save_server_avatar(from_user, avatar_name, avatar_data)
            self.add_chat_item("private", from_user)
            if image_name and image_data:
                saved = self._save_incoming_photo(from_user, image_name, image_data)
                self._append_local_entry("private", from_user, {"kind": "photo", "from": from_user, "text": text, "file": saved or image_name, "ts": self._now(), "mine": False})
            elif text:
                self._append_local_entry("private", from_user, {"kind": "text", "from": from_user, "text": text, "ts": self._now(), "mine": False})
            if self.current_chat_type == "private" and self.current_chat_name == from_user:
                self._render_local_chat()
            return

        if msg_type == "group":
            group = data.get("group", "group")
            from_user = data.get("from", "unknown")
            text = data.get("message", "")
            image_name = data.get("image_name")
            image_data = data.get("image_data")
            avatar_name = data.get("avatar_name")
            avatar_data = data.get("avatar_data")
            if avatar_name and avatar_data:
                self._save_server_avatar(from_user, avatar_name, avatar_data)
            self.add_chat_item("group", group)
            if image_name and image_data:
                saved = self._save_incoming_photo(from_user, image_name, image_data)
                self._append_local_entry("group", group, {"kind": "photo", "from": from_user, "text": text, "file": saved or image_name, "ts": self._now(), "mine": False})
            elif text:
                self._append_local_entry("group", group, {"kind": "text", "from": from_user, "text": text, "ts": self._now(), "mine": False})
            if self.current_chat_type == "group" and self.current_chat_name == group:
                self._render_local_chat()


def main():
    root = ctk.CTk()
    NanogramGUI(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        error_text = traceback.format_exc()
        try:
            with open("client_gui_error.log", "w", encoding="utf-8") as log_file:
                log_file.write(error_text)
        except Exception:
            pass
        try:
            messagebox.showerror("Error", f"Unexpected error:\n{exc}\n\nDetails have been written to client_gui_error.log")
        except Exception:
            print(error_text)
        raise
