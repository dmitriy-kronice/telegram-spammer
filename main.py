import os
import logging
from flask import Flask, render_template, request, jsonify
from flask_session import Session
import asyncio
import threading
import json
from spammer import TelegramSpammer
from flask_cors import CORS



# Настройка логов
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app) 
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-this')
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

# Инициализация спамера
try:
    spammer = TelegramSpammer()
    logger.info("✅ Spammer инициализирован")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации: {e}")
    spammer = None

# Для запуска асинхронных операций
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status')
def get_status():
    """Получить статус"""
    try:
        if not spammer:
            return jsonify({
                'success': False,
                'error': 'Spammer не инициализирован'
            })
        
        try:
            status = spammer.get_status()
        except AttributeError:
            status = {
                'running': False,
                'paused': False,
                'groups_count': len(spammer.groups) if hasattr(spammer, 'groups') else 0,
                'groups': spammer.groups if hasattr(spammer, 'groups') else [],
                'message_text': spammer.config.get('message_text', '') if hasattr(spammer, 'config') else '',
                'interval': spammer.config.get('interval', 3600) if hasattr(spammer, 'config') else 3600,
                'enabled': spammer.config.get('enabled', False) if hasattr(spammer, 'config') else False,
                'delay_between_groups': spammer.config.get('delay_between_groups', 3) if hasattr(spammer, 'config') else 3,
                'max_messages_per_hour': spammer.config.get('max_messages_per_hour', 30) if hasattr(spammer, 'config') else 30,
                'is_connected': spammer.client and spammer.client.is_connected() if spammer.client else False,
                'is_authorized': spammer.config.get('is_authorized', False) if hasattr(spammer, 'config') else False,
                'phone': spammer.config.get('phone', '') if hasattr(spammer, 'config') else '',
                'auth_waiting': spammer._auth_waiting if hasattr(spammer, '_auth_waiting') else False
            }
        
        return jsonify({
            'success': True,
            'status': status
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if not spammer:
        return jsonify({'success': False, 'error': 'Spammer не инициализирован'})

    if request.method == 'GET':
        return jsonify({'success': True, 'config': spammer.config})

    elif request.method == 'POST':
        data = request.json

        if 'api_id' in data:
            spammer.config['api_id'] = int(data['api_id']) if data['api_id'] else 0
        if 'api_hash' in data:
            spammer.config['api_hash'] = data['api_hash']
        if 'message_text' in data:
            spammer.config['message_text'] = data['message_text']
        if 'interval' in data:
            spammer.config['interval'] = int(data['interval']) if data['interval'] else 3600
        if 'delay_between_groups' in data:
            spammer.config['delay_between_groups'] = int(data['delay_between_groups']) if data[
                'delay_between_groups'] else 3
        if 'max_messages_per_hour' in data:
            spammer.config['max_messages_per_hour'] = int(data['max_messages_per_hour']) if data[
                'max_messages_per_hour'] else 30
        if 'enabled' in data:
            spammer.config['enabled'] = bool(data['enabled'])

        spammer.save_config()
        return jsonify({'success': True, 'message': 'Конфигурация обновлена'})


@app.route('/api/groups', methods=['GET', 'POST', 'DELETE'])
def handle_groups():
    if not spammer:
        return jsonify({'success': False, 'error': 'Spammer не инициализирован'})

    if request.method == 'GET':
        return jsonify({'success': True, 'groups': spammer.groups})

    elif request.method == 'POST':
        data = request.json
        group = data.get('group', '').strip()

        if not group:
            return jsonify({'success': False, 'error': 'Группа не указана'})

        if group not in spammer.groups:
            spammer.groups.append(group)
            spammer.save_groups()

        return jsonify({'success': True, 'message': f'Группа {group} добавлена', 'groups': spammer.groups})

    elif request.method == 'DELETE':
        data = request.json
        group = data.get('group', '').strip()

        if group in spammer.groups:
            spammer.groups.remove(group)
            spammer.save_groups()

        return jsonify({'success': True, 'message': f'Группа {group} удалена', 'groups': spammer.groups})


@app.route('/api/auth/send', methods=['POST'])
def send_auth_code():
    if not spammer:
        return jsonify({'success': False, 'error': 'Spammer не инициализирован'})

    data = request.json
    phone = data.get('phone', '').strip()

    if not phone:
        return jsonify({'success': False, 'error': 'Номер телефона не указан'})

    def run_async():
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(spammer.send_auth_code(phone))

    success, message = run_async()
    return jsonify({'success': success, 'message': message})


@app.route('/api/auth/verify', methods=['POST'])
def verify_auth_code():
    if not spammer:
        return jsonify({'success': False, 'error': 'Spammer не инициализирован'})

    data = request.json
    code = data.get('code', '').strip()

    if not code:
        return jsonify({'success': False, 'error': 'Код не указан'})

    def run_async():
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(spammer.verify_auth_code(code))

    success, message = run_async()
    return jsonify({'success': success, 'message': message})

@app.route('/api/auth/status')
def auth_status():
    """Проверить статус авторизации"""
    try:
        if not spammer:
            return jsonify({
                'success': False,
                'error': 'Spammer не инициализирован'
            })
        
        try:
            status = spammer.get_status()
        except AttributeError:
            # Если метода нет - возвращаем базовый статус
            status = {
                'running': False,
                'paused': False,
                'groups_count': len(spammer.groups) if hasattr(spammer, 'groups') else 0,
                'groups': spammer.groups if hasattr(spammer, 'groups') else [],
                'message_text': spammer.config.get('message_text', '') if hasattr(spammer, 'config') else '',
                'interval': 3600,
                'enabled': False,
                'delay_between_groups': 3,
                'max_messages_per_hour': 30,
                'is_connected': False,
                'is_authorized': False,
                'phone': '',
                'auth_waiting': False
            }
        
        return jsonify({
            'success': True,
            'is_authorized': status.get('is_authorized', False),
            'phone': status.get('phone', ''),
            'auth_waiting': status.get('auth_waiting', False)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/api/start', methods=['POST'])
def start_spam():
    if not spammer:
        return jsonify({'success': False, 'error': 'Spammer не инициализирован'})

    # Проверки перед запуском
    if not spammer.config.get('api_id') or not spammer.config.get('api_hash'):
        return jsonify({'success': False, 'error': 'Не указаны API данные'})

    if not spammer.config.get('message_text'):
        return jsonify({'success': False, 'error': 'Не указан текст сообщения'})

    if not spammer.groups:
        return jsonify({'success': False, 'error': 'Нет добавленных групп'})

    if not spammer.config.get('is_authorized'):
        return jsonify({'success': False, 'error': 'Не выполнена авторизация'})

    def run_async():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(spammer.start())

    thread = threading.Thread(target=run_async)
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'message': 'Рассылка запущена'})


@app.route('/api/stop', methods=['POST'])
def stop_spam():
    if not spammer:
        return jsonify({'success': False, 'error': 'Spammer не инициализирован'})

    def run_async():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(spammer.stop())

    thread = threading.Thread(target=run_async)
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'message': 'Рассылка остановлена'})


@app.route('/api/pause', methods=['POST'])
def pause_spam():
    if not spammer:
        return jsonify({'success': False, 'error': 'Spammer не инициализирован'})

    spammer.pause()
    return jsonify({'success': True, 'message': 'Рассылка на паузе'})


@app.route('/api/resume', methods=['POST'])
def resume_spam():
    if not spammer:
        return jsonify({'success': False, 'error': 'Spammer не инициализирован'})

    spammer.resume()
    return jsonify({'success': True, 'message': 'Рассылка продолжена'})


@app.route('/api/test', methods=['POST'])
def test_message():
    if not spammer:
        return jsonify({'success': False, 'error': 'Spammer не инициализирован'})

    data = request.json
    group = data.get('group', '').strip()
    message = data.get('message', '').strip()

    if not group or not message:
        return jsonify({'success': False, 'error': 'Группа и сообщение обязательны'})

    def run_async():
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(spammer.send_to_group(group, message))

    success, error = run_async()
    return jsonify({'success': success, 'message': 'Отправлено' if success else error})


@app.route('/api/clear_groups', methods=['POST'])
def clear_groups():
    if not spammer:
        return jsonify({'success': False, 'error': 'Spammer не инициализирован'})

    spammer.groups = []
    spammer.save_groups()
    return jsonify({'success': True, 'message': 'Все группы удалены'})


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
