import json
import socket
import threading

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 12345


def listen_server(sock: socket.socket):
    with sock.makefile("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                data = json.loads(line.strip())
            except json.JSONDecodeError:
                print("[server] invalid response")
                continue
            status = data.get("status")
            msg = data.get("message")
            payload = {k: v for k, v in data.items() if k not in {"status", "message"}}
            if payload:
                print(f"[server] {status}: {msg} {payload}")
            else:
                print(f"[server] {status}: {msg}")


def send_message(sock: socket.socket, payload: dict):
    raw = json.dumps(payload, ensure_ascii=False) + "\n"
    sock.sendall(raw.encode("utf-8"))


def print_help():
    print("Commands:")
    print("  /register username password")
    print("  /login username password")
    print("  /msg target message")
    print("  /group create groupname member1,member2,...")
    print("  /group send groupname message")
    print("  /users")
    print("  /groups")
    print("  /help")
    print("  /quit")


def main():
    print(f"Connecting to {SERVER_HOST}:{SERVER_PORT}...")
    with socket.create_connection((SERVER_HOST, SERVER_PORT)) as sock:
        listener = threading.Thread(target=listen_server, args=(sock,), daemon=True)
        listener.start()
        print_help()
        while True:
            try:
                line = input("> ")
            except EOFError:
                break
            if not line.strip():
                continue
            if line.startswith("/register "):
                _, username, password = line.split(maxsplit=2)
                send_message(sock, {"action": "register", "username": username, "password": password})
            elif line.startswith("/login "):
                _, username, password = line.split(maxsplit=2)
                send_message(sock, {"action": "login", "username": username, "password": password})
            elif line.startswith("/msg "):
                _, recipient, message = line.split(maxsplit=2)
                send_message(sock, {"action": "private", "to": recipient, "message": message})
            elif line.startswith("/group create "):
                parts = line.split(maxsplit=3)
                if len(parts) != 4:
                    print("Usage: /group create groupname member1,member2,...")
                    continue
                _, _, group_name, members = parts
                member_list = [m.strip() for m in members.split(",") if m.strip()]
                send_message(sock, {"action": "create_group", "group": group_name, "members": member_list})
            elif line.startswith("/group send "):
                parts = line.split(maxsplit=3)
                if len(parts) != 4:
                    print("Usage: /group send groupname message")
                    continue
                _, _, group_name, message = parts
                send_message(sock, {"action": "group", "group": group_name, "message": message})
            elif line.strip() == "/users":
                send_message(sock, {"action": "list_users"})
            elif line.strip() == "/groups":
                send_message(sock, {"action": "list_groups"})
            elif line.strip() == "/help":
                print_help()
            elif line.strip() == "/quit":
                break
            else:
                print("Unknown command. Type /help")


if __name__ == "__main__":
    main()
