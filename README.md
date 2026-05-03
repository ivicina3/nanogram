# nanogram
Простой чат-мессенджер на Python с серверной частью.

## Запуск сервера

```bash
python server.py
```

Сервер слушает на `127.0.0.1:12345` и хранит пользователей в файле `chat.db`.

## Запуск клиента

```bash
python client.py
```

## Команды клиента

- `/register username password` — регистрация нового пользователя
- `/login username password` — авторизация
- `/msg target message` — отправить личное сообщение
- `/group create groupname member1,member2,...` — создать группу и добавить участников
- `/group send groupname message` — отправить сообщение в группу
- `/users` — получить список всех пользователей
- `/groups` — получить список всех групп
- `/help` — помощь
- `/quit` — выход
