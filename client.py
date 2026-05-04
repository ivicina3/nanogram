import argparse
import json
import socket
import threading

DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_REMOTE_HOST = "195.208.118.78"
DEFAULT_SERVER_PORT = 12345


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
    print("  connect host [port]  - connect to server (default port: 12345)")
    print("  register username password")
    print("  login username password")
    print("  msg target message")
    print("  group create groupname member1,member2,...")
    print("  group send groupname message")
    print("  history private username [limit]")
    print("  history group groupname [limit]")
    print("  users")
    print("  groups")
    print("  help")
    print("  quit")


def parse_command_args(line: str, min_parts: int, usage: str):
    parts = line.split(maxsplit=min_parts)
    if len(parts) <= min_parts:
        print(usage)
        return None
    return parts


def parse_args():
    parser = argparse.ArgumentParser(description="Nanogram chat client")
    parser.add_argument("--host", default=None, help="Server IP or hostname")
    parser.add_argument("--port", type=int, default=DEFAULT_SERVER_PORT, help="Server TCP port")
    return parser.parse_args()


def connect_to_server(host: str, port: int) -> socket.socket:
    print(f"Connecting to {host}:{port}...")
    sock = socket.create_connection((host, port))
    listener = threading.Thread(target=listen_server, args=(sock,), daemon=True)
    listener.start()
    return sock


def main():
    args = parse_args()
    sock = None
    if args.host:
        sock = connect_to_server(args.host, args.port)
    else:
        print("No server specified. Use connect host port or run with --host <host> --port <port>.")
    print_help()
    while True:
        try:
            line = input("> ")
        except EOFError:
            break
        if not line.strip():
            continue
        if line.startswith("connect "):
            parts = line.split(maxsplit=2)
            if len(parts) < 2:
                print("Usage: connect host [port]")
                continue
            host = parts[1]
            port = DEFAULT_SERVER_PORT
            if len(parts) == 3:
                try:
                    port = int(parts[2])
                except ValueError:
                    print("Port must be a number")
                    continue
            if sock:
                print("Closing previous connection")
                sock.close()
            try:
                sock = connect_to_server(host, port)
            except Exception as exc:
                print(f"Connection failed: {exc}")
                sock = None
            continue
        if line.strip() == "connect":
            if sock:
                print("Already connected")
            else:
                print("Usage: connect host [port]")
            continue
        if line.startswith("register "):
            if sock is None:
                print("Connect to a server first with connect host port")
                continue
            parts = parse_command_args(line, 2, "Usage: register username password")
            if parts is None:
                continue
            _, username, password = parts
            send_message(sock, {"action": "register", "username": username, "password": password})
        elif line.startswith("login "):
            if sock is None:
                print("Connect to a server first with connect host port")
                continue
            parts = parse_command_args(line, 2, "Usage: login username password")
            if parts is None:
                continue
            _, username, password = parts
            send_message(sock, {"action": "login", "username": username, "password": password})
        elif line.startswith("msg "):
            if sock is None:
                print("Connect to a server first with connect host port")
                continue
            parts = parse_command_args(line, 2, "Usage: msg target message")
            if parts is None:
                continue
            _, recipient, message = parts
            send_message(sock, {"action": "private", "to": recipient, "message": message})
        elif line.startswith("group create "):
            if sock is None:
                print("Connect to a server first with connect host port")
                continue
            parts = line.split(maxsplit=3)
            if len(parts) != 4:
                print("Usage: group create groupname member1,member2,...")
                continue
            _, _, group_name, members = parts
            member_list = [m.strip() for m in members.split(",") if m.strip()]
            if not member_list:
                print("Usage: group create groupname member1,member2,...")
                continue
            send_message(sock, {"action": "create_group", "group": group_name, "members": member_list})
        elif line.startswith("group send "):
            if sock is None:
                print("Connect to a server first with connect host port")
                continue
            parts = parse_command_args(line, 3, "Usage: group send groupname message")
            if parts is None:
                continue
            _, _, group_name, message = parts
            send_message(sock, {"action": "group", "group": group_name, "message": message})
        elif line.startswith("history private "):
            if sock is None:
                print("Connect to a server first with connect host port")
                continue
            parts = line.split(maxsplit=3)
            if len(parts) < 3:
                print("Usage: history private username [limit]")
                continue
            peer = parts[2]
            limit = 50
            if len(parts) == 4:
                try:
                    limit = int(parts[3])
                except ValueError:
                    print("Limit must be a number")
                    continue
            send_message(sock, {"action": "history_private", "with": peer, "limit": limit})
        elif line.startswith("history group "):
            if sock is None:
                print("Connect to a server first with connect host port")
                continue
            parts = line.split(maxsplit=3)
            if len(parts) < 3:
                print("Usage: history group groupname [limit]")
                continue
            group_name = parts[2]
            limit = 50
            if len(parts) == 4:
                try:
                    limit = int(parts[3])
                except ValueError:
                    print("Limit must be a number")
                    continue
            send_message(sock, {"action": "history_group", "group": group_name, "limit": limit})
        elif line.strip() == "users":
            if sock is None:
                print("Connect to a server first with connect host port")
                continue
            send_message(sock, {"action": "list_users"})
        elif line.strip() == "groups":
            if sock is None:
                print("Connect to a server first with connect host port")
                continue
            send_message(sock, {"action": "list_groups"})
        elif line.strip() == "help":
            print_help()
        elif line.strip() == "quit":
            break
        else:
            print("Unknown command. Type help")


if __name__ == "__main__":
    main()
