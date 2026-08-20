import asyncio
import json
import logging
import time
import os
from typing import Tuple
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TelegramSpammer:
    def __init__(self, config_file='config.json', groups_file='groups.json'):
        self.config_file = config_file
        self.groups_file = groups_file
        self.client = None
        self.is_running = False
        self.is_paused = False
        self.task = None
        self.sent_count = 0
        self.last_sent_time = 0
        self._auth_phone = None
        self._auth_code_hash = None
        
        self.ensure_files()
        self.load_config()
        self.load_groups()
        
    def ensure_files(self):
        if not os.path.exists(self.config_file):
            default = {
                "api_id": 0,
                "api_hash": "",
                "phone": "",
                "message_text": "Привет!",
                "interval": 10,
                "delay": 3,
                "max_per_hour": 30,
                "enabled": False,
                "is_authorized": False,
                "session_string": ""
            }
            with open(self.config_file, 'w') as f:
                json.dump(default, f, indent=2)
                
        if not os.path.exists(self.groups_file):
            with open(self.groups_file, 'w') as f:
                json.dump([], f, indent=2)
                
    def load_config(self):
        with open(self.config_file, 'r') as f:
            self.config = json.load(f)
            
    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
            
    def load_groups(self):
        with open(self.groups_file, 'r') as f:
            self.groups = json.load(f)
            
    def save_groups(self):
        with open(self.groups_file, 'w') as f:
            json.dump(self.groups, f, indent=2)
            
    # ====== АВТОРИЗАЦИЯ ======
    async def send_auth_code(self, phone: str) -> Tuple[bool, str]:
        try:
            self._auth_phone = phone
            
            self.client = TelegramClient(
                StringSession(self.config.get('session_string', '')),
                self.config['api_id'],
                self.config['api_hash']
            )
            await self.client.connect()
            
            if await self.client.is_user_authorized():
                self.config['phone'] = phone
                self.config['is_authorized'] = True
                self.config['session_string'] = StringSession.save(self.client.session)
                self.save_config()
                return True, "Уже авторизован"
            
            result = await self.client.send_code_request(phone)
            self._auth_code_hash = result.phone_code_hash
            return True, "Код отправлен!"
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False, str(e)
            
    async def verify_auth_code(self, code: str) -> Tuple[bool, str]:
        try:
            if not self.client:
                return False, "Клиент не создан"
                
            await self.client.sign_in(
                phone=self._auth_phone,
                code=code,
                phone_code_hash=self._auth_code_hash
            )
            
            self.config['phone'] = self._auth_phone
            self.config['is_authorized'] = True
            self.config['session_string'] = StringSession.save(self.client.session)
            self.save_config()
            
            logger.info("✅ Авторизация успешна!")
            return True, "Авторизация успешна!"
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False, str(e)
            
    # ====== ОТПРАВКА (С ПЕРЕСОЗДАНИЕМ КЛИЕНТА) ======
    async def send_message(self, chat_id: str, text: str) -> bool:
        try:
            # СОЗДАЕМ НОВЫЙ КЛИЕНТ ДЛЯ КАЖДОЙ ОТПРАВКИ
            logger.info(f"📤 Создаю клиент для {chat_id}...")
            
            client = TelegramClient(
                StringSession(self.config.get('session_string', '')),
                self.config['api_id'],
                self.config['api_hash']
            )
            
            # ТАЙМАУТ НА ПОДКЛЮЧЕНИЕ
            await asyncio.wait_for(client.connect(), timeout=10)
            logger.info(f"✅ Подключен для {chat_id}")
            
            # ТАЙМАУТ НА АВТОРИЗАЦИЮ
            if not await client.is_user_authorized():
                if self.config.get('phone'):
                    await asyncio.wait_for(
                        client.sign_in(phone=self.config['phone']),
                        timeout=10
                    )
            
            # ТАЙМАУТ НА ОТПРАВКУ
            logger.info(f"📤 Отправляю в {chat_id}...")
            await asyncio.wait_for(
                client.send_message(chat_id, text),
                timeout=15
            )
            logger.info(f"✅ Отправлено в {chat_id}")
            
            # Закрываем соединение
            await client.disconnect()
            return True
            
        except asyncio.TimeoutError:
            logger.error(f"❌ ТАЙМАУТ для {chat_id}")
            return False
        except errors.FloodWaitError as e:
            logger.warning(f"⚠️ FloodWait {e.seconds} сек")
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка {chat_id}: {e}")
            return False
            
    # ====== ЦИКЛ РАССЫЛКИ ======
    async def spam_loop(self):
        logger.info("🔄 Цикл запущен")
        
        while self.is_running:
            try:
                if self.is_paused:
                    await asyncio.sleep(2)
                    continue
                    
                if not self.config.get('enabled', False):
                    await asyncio.sleep(5)
                    continue
                    
                if not self.groups:
                    await asyncio.sleep(10)
                    continue
                    
                text = self.config.get('message_text', '')
                if not text:
                    await asyncio.sleep(10)
                    continue
                
                logger.info(f"📤 Отправка в {len(self.groups)} групп")
                
                for chat in self.groups:
                    if not self.is_running:
                        break
                        
                    logger.info(f"📤 В {chat}...")
                    success = await self.send_message(chat, text)
                    
                    if success:
                        self.sent_count += 1
                        
                    await asyncio.sleep(self.config.get('delay', 3))
                    
                self.sent_count = 0
                
            except Exception as e:
                logger.error(f"❌ Ошибка цикла: {e}")
                
            await asyncio.sleep(self.config.get('interval', 10))
            
    # ====== УПРАВЛЕНИЕ ======
    async def start(self):
        if self.is_running:
            return
            
        try:
            # Проверяем что есть сессия
            if not self.config.get('session_string'):
                logger.error("❌ Нет сохраненной сессии! Авторизуйтесь через веб-интерфейс")
                return
                
            # Проверяем что есть телефон
            if not self.config.get('phone'):
                logger.error("❌ Нет телефона!")
                return
                
            self.is_running = True
            self.task = asyncio.create_task(self.spam_loop())
            logger.info("🚀 Запущено!")
            
        except Exception as e:
            logger.error(f"❌ Ошибка старта: {e}")
            self.is_running = False
            
    async def stop(self):
        self.is_running = False
        if self.task:
            self.task.cancel()
        logger.info("🛑 Остановлено")
        
    def pause(self):
        self.is_paused = True
        logger.info("⏸️ Пауза")
        
    def resume(self):
        self.is_paused = False
        logger.info("▶️ Продолжено")
        
    def get_status(self):
        return {
            'running': self.is_running,
            'paused': self.is_paused,
            'groups_count': len(self.groups),
            'groups': self.groups,
            'message_text': self.config.get('message_text', ''),
            'interval': self.config.get('interval', 10),
            'enabled': self.config.get('enabled', False),
            'delay_between_groups': self.config.get('delay', 3),
            'is_connected': bool(self.client and self.client.is_connected()) if self.client else False,
            'is_authorized': self.config.get('is_authorized', False),
            'phone': self.config.get('phone', '')
        }
        
    # ====== АЛИАС ======
    async def send_to_group(self, group: str, message: str) -> Tuple[bool, str]:
        success = await self.send_message(group, message)
        return success, "OK" if success else "Ошибка"
