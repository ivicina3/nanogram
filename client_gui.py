import json
import socket
import threading
import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext, ttk

DEFAULT_SERVER_HOST = "195.208.118.78"
DEFAULT_SERVER_PORT = 12345


class NanogramGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Nanogram Chat")
        self.root.geometry("760x760")
        self.sock = None
        self.username = None
        self.listener_thread = None
        self.listener_running = False
        self.receive_buffer = ""

        self.configure_style()
        self.create_widgets()
        self.set_connection_state(False)
        self.root.after(100, self.auto_connect)

    def configure_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TLabelFrame", background="#f3f6fb", borderwidth=1, relief="solid")
        style.configure("TLabel", background="#f3f6fb", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=6)
        style.configure("TEntry", font=("Segoe UI", 10))
        style.configure("Status.TLabel", foreground="#3d3d3d", font=("Segoe UI", 9, "italic"))
        style.configure("Header.TLabel", font=("Segoe UI Semibold", 11))

    def create_widgets(self):
        self.root.configure(background="#eaf0f6")

        # Connection frame
        conn_frame = ttk.LabelFrame(self.root, text="Connection", padding=12)
        conn_frame.pack(fill="x", padx=10, pady=(10, 5))
        conn_frame.columnconfigure(1, weight=1)

        ttk.Label(conn_frame, text="Host:", style="Header.TLabel").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.host_entry = ttk.Entry(conn_frame)
        self.host_entry.insert(0, DEFAULT_SERVER_HOST)
        self.host_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(conn_frame, text="Port:", style="Header.TLabel").grid(row=0, column=2, sticky="e", padx=5, pady=5)
        self.port_entry = ttk.Entry(conn_frame, width=12)
        self.port_entry.insert(0, str(DEFAULT_SERVER_PORT))
        self.port_entry.grid(row=0, column=3, sticky="w", padx=5, pady=5)

        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.connect)
        self.connect_btn.grid(row=0, column=4, sticky="e", padx=5, pady=5)

        # Authentication frame

        # Authentication frame
        auth_frame = ttk.LabelFrame(self.root, text="Authentication", padding=12)
        auth_frame.pack(fill="x", padx=10, pady=5)
        auth_frame.columnconfigure(1, weight=1)
        auth_frame.columnconfigure(3, weight=1)

        ttk.Label(auth_frame, text="Username:", style="Header.TLabel").grid(row=0, column=0, sticky="e", padx=5, pady=6)
        self.user_entry = ttk.Entry(auth_frame)
        self.user_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=6)

        ttk.Label(auth_frame, text="Password:", style="Header.TLabel").grid(row=0, column=2, sticky="e", padx=5, pady=6)
        self.pass_entry = ttk.Entry(auth_frame, show="*")
        self.pass_entry.grid(row=0, column=3, sticky="ew", padx=5, pady=6)

        self.register_btn = ttk.Button(auth_frame, text="Register", command=self.register)
        self.register_btn.grid(row=0, column=4, padx=5, pady=6)
        self.login_btn = ttk.Button(auth_frame, text="Login", command=self.login)
        self.login_btn.grid(row=0, column=5, padx=5, pady=6)

        # Chat frame
        chat_frame = ttk.LabelFrame(self.root, text="Chat", padding=12)
        chat_frame.pack(fill="both", expand=True, padx=10, pady=5)
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(1, weight=1)

        ttk.Label(chat_frame, text="Messages:", style="Header.TLabel").grid(row=0, column=0, sticky="w", padx=5)
        self.chat_display = scrolledtext.ScrolledText(chat_frame, state="disabled", wrap="word")
        self.chat_display.grid(row=1, column=0, sticky="nsew", padx=5, pady=(5, 10))

        # Message input frame
        msg_frame = ttk.Frame(chat_frame)
        msg_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        msg_frame.columnconfigure(1, weight=1)
        msg_frame.columnconfigure(3, weight=1)

        ttk.Label(msg_frame, text="Recipient:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.recipient_entry = ttk.Entry(msg_frame)
        self.recipient_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(msg_frame, text="Message:").grid(row=0, column=2, sticky="e", padx=5, pady=5)
        self.private_msg_entry = ttk.Entry(msg_frame)
        self.private_msg_entry.grid(row=0, column=3, sticky="ew", padx=5, pady=5)

        self.send_private_btn = ttk.Button(msg_frame, text="Send Private", command=self.send_private)
        self.send_private_btn.grid(row=0, column=4, padx=5, pady=5)

        # Group frame
        group_frame = ttk.LabelFrame(self.root, text="Groups", padding=12)
        group_frame.pack(fill="x", padx=10, pady=5)
        group_frame.columnconfigure(1, weight=1)
        group_frame.columnconfigure(3, weight=1)

        ttk.Label(group_frame, text="Group Name:", style="Header.TLabel").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.group_name_entry = ttk.Entry(group_frame)
        self.group_name_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(group_frame, text="Members:", style="Header.TLabel").grid(row=0, column=2, sticky="e", padx=5, pady=5)
        self.members_entry = ttk.Entry(group_frame)
        self.members_entry.grid(row=0, column=3, sticky="ew", padx=5, pady=5)

        self.create_group_btn = ttk.Button(group_frame, text="Create Group", command=self.create_group)
        self.create_group_btn.grid(row=0, column=4, padx=5, pady=5)

        ttk.Label(group_frame, text="Group Message:", style="Header.TLabel").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.group_msg_entry = ttk.Entry(group_frame)
        self.group_msg_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=5)

        self.send_group_btn = ttk.Button(group_frame, text="Send to Group", command=self.send_group)
        self.send_group_btn.grid(row=1, column=4, padx=5, pady=5)

        # Info frame
        info_frame = ttk.Frame(self.root)
        info_frame.pack(fill="x", padx=10, pady=(5, 10))

        self.list_users_btn = ttk.Button(info_frame, text="List Users", command=self.list_users)
        self.list_users_btn.pack(side="left", padx=5)
        self.list_groups_btn = ttk.Button(info_frame, text="List Groups", command=self.list_groups)
        self.list_groups_btn.pack(side="left", padx=5)
        self.disconnect_btn = ttk.Button(info_frame, text="Disconnect", command=self.disconnect)
        self.disconnect_btn.pack(side="left", padx=5)

        self.status_label = ttk.Label(info_frame, text="Disconnected", style="Status.TLabel")
        self.status_label.pack(side="right", padx=5)

    def log_message(self, msg: str):
        self.chat_display.config(state="normal")
        self.chat_display.insert("end", msg + "\n")
        self.chat_display.see("end")
        self.chat_display.config(state="disabled")

    def connect(self):
        if self.sock:
            self.log_message("[system] Already connected")
            return
        host = self.host_entry.get().strip()
        port_text = self.port_entry.get().strip()
        if not host or not port_text:
            messagebox.showerror("Error", "Host and port required")
            return
        try:
            port = int(port_text)
        except ValueError:
            messagebox.showerror("Error", "Port must be a number")
            return
        try:
            self.sock = socket.create_connection((host, port), timeout=10)
            self.sock.setblocking(True)
            self.listener_running = True
            self.status_label.config(text=f"Connected to {host}:{port}")
            self.log_message(f"[system] Connected to {host}:{port}")
            self.set_connection_state(True)
            self.listener_thread = threading.Thread(target=self.listen_server, daemon=True)
            self.listener_thread.start()
        except Exception as e:
            self.sock = None
            self.listener_running = False
            self.set_connection_state(False)
            messagebox.showerror("Connection Error", str(e))

    def auto_connect(self):
        host = self.host_entry.get().strip()
        port_text = self.port_entry.get().strip()
        if not host or not port_text:
            return
        try:
            port = int(port_text)
        except ValueError:
            return
        self.log_message("[system] Auto-connecting...")
        try:
            self.sock = socket.create_connection((host, port), timeout=10)
            self.sock.setblocking(True)
            self.listener_running = True
            self.status_label.config(text=f"Connected to {host}:{port}")
            self.log_message(f"[system] Connected to {host}:{port}")
            self.set_connection_state(True)
            self.listener_thread = threading.Thread(target=self.listen_server, daemon=True)
            self.listener_thread.start()
        except Exception as e:
            self.sock = None
            self.listener_running = False
            self.set_connection_state(False)
            self.log_message(f"[system] Auto-connect failed: {e}")

    def listen_server(self):
        try:
            while self.listener_running and self.sock:
                try:
                    data = self.sock.recv(4096)
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
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        self.safe_log_message("[server] Invalid response")
                        continue
                    status = data.get("status")
                    msg = data.get("message")
                    msg_type = data.get("type")
                    if msg_type == "private":
                        from_user = data.get("from")
                        text = data.get("message")
                        self.safe_log_message(f"[private from {from_user}] {text}")
                    elif msg_type == "group":
                        group = data.get("group")
                        from_user = data.get("from")
                        text = data.get("message")
                        self.safe_log_message(f"[{group} from {from_user}] {text}")
                    else:
                        if msg:
                            self.safe_log_message(f"[{status}] {msg}")
        finally:
            self.root.after(0, self.on_disconnect)

    def safe_log_message(self, msg: str):
        self.root.after(0, lambda: self.log_message(msg))

    def on_disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self.listener_running = False
        self.set_connection_state(False)
        self.status_label.config(text="Disconnected")
        self.log_message("[system] Disconnected")

    def send_message(self, payload: dict):
        if not self.sock:
            messagebox.showerror("Error", "Not connected to server")
            return
        try:
            raw = json.dumps(payload, ensure_ascii=False) + "\n"
            self.sock.sendall(raw.encode("utf-8"))
        except Exception as e:
            self.safe_log_message(f"[system] Send failed: {e}")
            self.on_disconnect()

    def register(self):
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()
        if not username or not password:
            messagebox.showerror("Error", "Username and password required")
            return
        self.send_message({"action": "register", "username": username, "password": password})

    def login(self):
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()
        if not username or not password:
            messagebox.showerror("Error", "Username and password required")
            return
        self.username = username
        self.send_message({"action": "login", "username": username, "password": password})

    def send_private(self):
        recipient = self.recipient_entry.get().strip()
        msg_text = self.private_msg_entry.get().strip()
        if not recipient or not msg_text:
            messagebox.showerror("Error", "Recipient and message required")
            return
        self.send_message({"action": "private", "to": recipient, "message": msg_text})
        self.private_msg_entry.delete(0, "end")

    def create_group(self):
        name = self.group_name_entry.get().strip()
        members_text = self.members_entry.get().strip()
        if not name or not members_text:
            messagebox.showerror("Error", "Group name and members required")
            return
        members = [m.strip() for m in members_text.split(",") if m.strip()]
        if not members:
            messagebox.showerror("Error", "At least one member required")
            return
        self.send_message({"action": "create_group", "group": name, "members": members})

    def send_group(self):
        group = self.group_name_entry.get().strip()
        message = self.group_msg_entry.get().strip()
        if not group or not message:
            messagebox.showerror("Error", "Group name and message required")
            return
        self.send_message({"action": "group", "group": group, "message": message})

    def list_users(self):
        self.send_message({"action": "list_users"})

    def list_groups(self):
        self.send_message({"action": "list_groups"})

    def disconnect(self):
        self.listener_running = False
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self.set_connection_state(False)
        self.status_label.config(text="Disconnected")
        self.log_message("[system] Disconnected")

    def set_connection_state(self, connected: bool):
        host_state = "disabled" if connected else "normal"
        action_state = "normal" if connected else "disabled"
        self.host_entry.config(state=host_state)
        self.port_entry.config(state=host_state)
        self.register_btn.config(state=action_state)
        self.login_btn.config(state=action_state)
        self.send_private_btn.config(state=action_state)
        self.create_group_btn.config(state=action_state)
        self.send_group_btn.config(state=action_state)
        self.list_users_btn.config(state=action_state)
        self.list_groups_btn.config(state=action_state)
        self.disconnect_btn.config(state=action_state)
        self.connect_btn.config(text="Disconnect" if connected else "Connect")
        self.connect_btn.config(command=self.disconnect if connected else self.connect)


if __name__ == "__main__":
    root = tk.Tk()
    app = NanogramGUI(root)
    root.mainloop()
