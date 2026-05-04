# nanogram
Простой чат-мессенджер на Python с серверной частью.

## Запуск сервера

```bash
python server.py
```

Сервер слушает на `127.0.0.1:12345` и хранит пользователей в файле `chat.db`.

## Запуск клиента

### Текстовый клиент

```bash
python client.py
```

Внутри клиента подключитесь командой (порт по умолчанию 12345):

```text
/connect 195.208.118.78
```

Или с другим портом:

```text
/connect 195.208.118.78 12345
```

Также можно подключиться сразу при запуске:

```bash
python client.py --host 195.208.118.78 --port 12345
```

### GUI-клиент (Tkinter)

```bash
python client_gui.py
```

Удобный графический интерфейс с полями для подключения, регистрации, отправки сообщений и создания групп.

### Создание исполняемого файла (.exe)

Чтобы использовать клиент без установки Python, компилируйте в .exe через PyInstaller.
Если команда `pyinstaller` не найдена, используйте Python напрямую:

```bash
pip install pyinstaller
C:\Users\ivic\AppData\Local\Python\pythoncore-3.14-64\python.exe -m PyInstaller --onefile client_gui.py
```

Исполняемый файл будет в папке `dist/`.

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
