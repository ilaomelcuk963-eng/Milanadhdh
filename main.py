import os
import requests
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Разрешает запросы с вашего index.html к этому серверу

# --- НАСТРОЙКИ GITHUB ---
# Важно: Для безопасности храните токен в переменных окружения, а не прямо в коде.
# Но для простоты примера мы оставим его здесь.
GITHUB_TOKEN = 'ВАШ_GITHUB_TOKEN'
GITHUB_USER = 'ВАШ_GITHUB_ЛОГИН'
GITHUB_REPO = 'ИМЯ_ВАШЕГО_РЕПОЗИТОРИЯ' # Например, 'doll-shop-data'
FILE_PATH = 'data.json'
API_URL = f'https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{FILE_PATH}'

# Пароль для доступа к действиям администратора
ADMIN_PASSWORD = '1488'

# --- ХЕЛПЕРЫ GITHUB API ---

def get_github_file():
    """Получает содержимое файла и его SHA с GitHub."""
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    try:
        r = requests.get(API_URL, headers=headers)
        r.raise_for_status()
        data = r.json()
        content = requests.get(data['download_url']).text
        return json.loads(content), data['sha']
    except requests.exceptions.RequestException as e:
        print(f"Ошибка получения файла с GitHub: {e}")
        return None, None

def update_github_file(content, sha, commit_message):
    """Обновляет файл на GitHub."""
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Content-Type': 'application/json'
    }
    # GitHub API требует содержимое в base64, но requests делает это автоматически для json-параметра
    # Для явного кодирования можно использовать: base64.b64encode(json.dumps(content).encode()).decode()
    data = {
        'message': commit_message,
        'content': json.dumps(content, indent=2, ensure_ascii=False),
        'sha': sha
    }
    try:
        r = requests.put(API_URL, headers=headers, json=data)
        r.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Ошибка обновления файла на GitHub: {e}")
        print(f"Ответ сервера: {r.text}")
        return False

# --- API ЭНДПОИНТЫ ---

@app.route('/api/data', methods=['GET'])
def get_all_data():
    """Отдает все данные из data.json."""
    content, _ = get_github_file()
    if content:
        return jsonify(content)
    return jsonify({"error": "Не удалось получить данные"}), 500

@app.route('/api/comments', methods=['POST'])
def add_comment():
    """Добавляет новый комментарий."""
    new_comment_data = request.json
    content, sha = get_github_file()
    if not content:
        return jsonify({"error": "Ошибка на сервере"}), 500

    new_comment = {
        'id': f'comment-{uuid.uuid4()}',
        'name': new_comment_data.get('name', 'Аноним'),
        'text': new_comment_data.get('text', ''),
        'rating': new_comment_data.get('rating', 5),
        'date': datetime.utcnow().isoformat() + "Z"
    }

    content['comments'].insert(0, new_comment) # Добавляем в начало списка

    if update_github_file(content, sha, 'Добавлен новый комментарий'):
        return jsonify(new_comment), 201
    return jsonify({"error": "Не удалось сохранить комментарий"}), 500

@app.route('/api/comments/<comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    """Удаляет комментарий по ID."""
    if request.headers.get('Admin-Password') != ADMIN_PASSWORD:
        return jsonify({"error": "Неавторизованный доступ"}), 403

    content, sha = get_github_file()
    if not content:
        return jsonify({"error": "Ошибка на сервере"}), 500

    initial_count = len(content['comments'])
    content['comments'] = [c for c in content['comments'] if c.get('id') != comment_id]
    
    if len(content['comments']) == initial_count:
        return jsonify({"error": "Комментарий не найден"}), 404

    if update_github_file(content, sha, f'Удален комментарий {comment_id}'):
        return jsonify({"success": True}), 200
    return jsonify({"error": "Не удалось удалить комментарий"}), 500
    
@app.route('/api/send-message', methods=['POST'])
def send_message():
    """Отправляет сообщение пользователю или всем."""
    if request.headers.get('Admin-Password') != ADMIN_PASSWORD:
        return jsonify({"error": "Неавторизованный доступ"}), 403
        
    data = request.json
    content, sha = get_github_file()
    if not content:
        return jsonify({"error": "Ошибка на сервере"}), 500
        
    new_message = {
        'id': f'msg-{uuid.uuid4()}',
        'recipient': data.get('recipient', 'global'),
        'text': data.get('text'),
        'timestamp': datetime.utcnow().timestamp()
    }
    content['messages'].append(new_message)
    
    if update_github_file(content, sha, 'Отправлено новое сообщение'):
        return jsonify(new_message), 201
    return jsonify({"error": "Не удалось отправить сообщение"}), 500

@app.route('/api/messages/<user_id>', methods=['GET'])
def get_messages(user_id):
    """Получает сообщения для конкретного пользователя и удаляет их."""
    content, sha = get_github_file()
    if not content:
        return jsonify({"error": "Ошибка на сервере"}), 500

    user_messages = []
    other_messages = []
    
    # Разделяем сообщения: те, что для пользователя, и все остальные
    for msg in content.get('messages', []):
        if msg['recipient'] == user_id or msg['recipient'] == 'global':
            user_messages.append(msg)
        else:
            other_messages.append(msg)
            
    if not user_messages:
        return jsonify([]), 200 # Нет сообщений, это не ошибка

    # Обновляем файл на GitHub, удаляя отданные сообщения
    content['messages'] = other_messages
    if update_github_file(content, sha, f'Доставлены сообщения для {user_id}'):
        return jsonify(user_messages)
    
    # Если обновить файл не удалось, не отдаем сообщения, чтобы они не потерялись
    return jsonify({"error": "Не удалось подтвердить доставку"}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
