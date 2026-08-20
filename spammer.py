import asyncio
import json
import logging
import time
import os
from typing import List, Dict, Optional, Tuple
from telethon import TelegramClient, errors

# Создаем папку для логов
os.makedirs('logs', exist_ok=True)

# Настройка логов
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/spam.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
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
        self._client_lock = asyncio.Lock()
        self._auth_phone = None
        self._auth_phone_code_hash = None
        self._auth_waiting = False

        self.ensure_files()
        self.load_config()
        self.load_groups()

    def ensure_files(self):
        os.makedirs('logs', exist_ok=True)

        if not os.path.exists(self.config_file):
            default_config = {
                "api_id": 0,
                "api_hash": "",
                "session_name": "spammer_session",
                "phone": "",
                "message_text": "🔥 Привет! Подписывайся на мой канал!",
                "interval": 10,
                "delay_between_groups": 3,
                "max_messages_per_hour": 30,
                "enabled": False,
                "is_authorized": False
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            logger.info("✅ Создан config.json")

        if not os.path.exists(self.groups_file):
            with open(self.groups_file, 'w', encoding='utf-8') as f:
                json.dump([], f, indent=2, ensure_ascii=False)
            logger.info("✅ Создан groups.json")

    def load_config(self):
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            logger.info("✅ Конфигурация загружена")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки конфига: {e}")
            self.config = {
                "api_id": 0,
                "api_hash": "",
                "session_name": "spammer_session",
                "phone": "",
                "message_text": "🔥 Привет! Подписывайся на мой канал!",
                "interval": 10,
                "delay_between_groups": 3,
                "max_messages_per_hour": 30,
                "enabled": False,
                "is_authorized": False
            }
            self.save_config()

    def save_config(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения конфига: {e}")

    def load_groups(self):
        try:
            with open(self.groups_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    self.groups = []
                else:
                    self.groups = json.loads(content)
            logger.info(f"✅ Загружено групп: {len(self.groups)}")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки групп: {e}")
            self.groups = []
            self.save_groups()

    def save_groups(self):
        try:
            with open(self.groups_file, 'w', encoding='utf-8') as f:
                json.dump(self.groups, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения групп: {e}")

    async def send_auth_code(self, phone: str) -> Tuple[bool, str]:
        try:
            self._auth_phone = phone
            self._auth_waiting = True

            if not self.config.get('api_id') or not self.config.get('api_hash'):
                return False, "API ID или API Hash не указаны!"

            if not self.client:
                self.client = TelegramClient(
                    self.config['session_name'],
                    self.config['api_id'],
                    self.config['api_hash']
                )

            if not self.client.is_connected():
                await self.client.connect()
                logger.info("✅ Клиент подключен")

            if await self.client.is_user_authorized():
                self.config['is_authorized'] = True
                self.config['phone'] = phone
                self.save_config()
                self._auth_waiting = False
                return True, "Уже авторизован"

            result = await self.client.send_code_request(phone)
            self._auth_phone_code_hash = result.phone_code_hash
            logger.info(f"✅ Код отправлен на {phone}")
            return True, "Код подтверждения отправлен на ваш номер"

        except errors.PhoneNumberInvalidError:
            return False, "Неверный номер телефона"
        except errors.FloodWaitError as e:
            return False, f"Слишком много попыток. Подождите {e.seconds} секунд"
        except Exception as e:
            logger.error(f"❌ Ошибка отправки кода: {e}")
            return False, f"Ошибка: {str(e)}"

    async def verify_auth_code(self, code: str) -> Tuple[bool, str]:
        try:
            if not self.client:
                return False, "Клиент не инициализирован"

            if not self._auth_phone_code_hash:
                return False, "Сначала запросите код"

            if not self.client.is_connected():
                await self.client.connect()

            await self.client.sign_in(
                phone=self._auth_phone,
                code=code,
                phone_code_hash=self._auth_phone_code_hash
            )

            self.config['phone'] = self._auth_phone
            self.config['is_authorized'] = True
            self.save_config()
            self._auth_waiting = False

            logger.info("✅ Авторизация успешна!")
            return True, "Авторизация успешна!"

        except errors.PhoneCodeInvalidError:
            return False, "Неверный код"
        except errors.PhoneCodeExpiredError:
            return False, "Код истек"
        except Exception as e:
            logger.error(f"❌ Ошибка подтверждения кода: {e}")
            return False, f"Ошибка: {str(e)}"
            
    async def _ensure_client(self) -> Tuple[bool, str]:
        async with self._client_lock:
            try:
                logger.info("🔍 _ensure_client: НАЧАЛО")
                
                if not self.config.get('api_id') or not self.config.get('api_hash'):
                    return False, "API ID или API Hash не указаны!"
                
                # ВСЕГДА СОЗДАЕМ НОВЫЙ КЛИЕНТ (старый глючный)
                if self.client:
                    try:
                        await self.client.disconnect()
                    except:
                        pass
                    self.client = None
                
                logger.info("🔍 _ensure_client: Создаю НОВЫЙ клиент")
                self.client = TelegramClient(
                    self.config['session_name'],
                    self.config['api_id'],
                    self.config['api_hash']
                )
                
                logger.info("🔍 _ensure_client: Подключаюсь...")
                await self.client.connect()
                logger.info("✅ _ensure_client: Клиент подключен")
                
                logger.info("🔍 _ensure_client: Проверяю авторизацию")
                if not await self.client.is_user_authorized():
                    logger.info("🔍 _ensure_client: Не авторизован")
                    if self.config.get('phone'):
                        logger.info(f"🔍 _ensure_client: Авторизуюсь по телефону {self.config['phone']}")
                        await self.client.start(phone=self.config['phone'])
                        self.config['is_authorized'] = True
                        self.save_config()
                        logger.info("✅ _ensure_client: Авторизован по сессии")
                    else:
                        return False, "Требуется авторизация"
                
                logger.info("✅ _ensure_client: УСПЕШНО")
                return True, "OK"
                
            except asyncio.TimeoutError:
                logger.error("❌ _ensure_client: ТАЙМАУТ!")
                return False, "Таймаут подключения к Telegram"
            except Exception as e:
                logger.error(f"❌ _ensure_client: Ошибка: {e}")
                return False, str(e)
    
        async def _get_client(self):
            success, error = await self._ensure_client()
            if not success:
                raise Exception(error)
            return self.client



    async def send_to_group(self, group: str, message: str) -> Tuple[bool, str]:
        try:
            # ВСЯ ОТПРАВКА С ТАЙМАУТОМ 15 СЕКУНД
            async with asyncio.timeout(15):
                logger.info(f"📤 send_to_group: Начинаю для {group}")
                
                # Пересоздаем клиент
                success, error = await self._ensure_client()
                if not success:
                    return False, error
                
                logger.info(f"📤 send_to_group: Клиент готов")
                
                # Проверка лимита
                max_msgs = self.config.get('max_messages_per_hour', 30)
                if self.sent_count >= max_msgs:
                    return False, f"Лимит {max_msgs} сообщений в час"
                
                # Задержка
                current_time = time.time()
                delay = self.config.get('delay_between_groups', 3)
                if current_time - self.last_sent_time < delay:
                    await asyncio.sleep(delay - (current_time - self.last_sent_time))
                
                # Отправляем напрямую
                logger.info(f"📤 send_to_group: Отправляю в {group}...")
                await self.client.send_message(group, message)
                logger.info(f"✅ send_to_group: Отправлено в {group}")
                
                self.sent_count += 1
                self.last_sent_time = time.time()
                return True, "OK"
                
        except asyncio.TimeoutError:
            logger.error(f"❌ send_to_group: ТАЙМАУТ для {group}")
            return False, "Таймаут 15 сек"
        except Exception as e:
            logger.error(f"❌ send_to_group: Ошибка: {e}")
            return False, str(e)

    async def spam_loop(self):
        logger.info("🔄 Запуск цикла рассылки")

        while self.is_running:
            try:
                if self.is_paused:
                    await asyncio.sleep(5)
                    continue

                if not self.config.get('enabled', False):
                    logger.info("⏸️ Рассылка отключена")
                    await asyncio.sleep(self.config.get('interval', 10))
                    continue

                if not self.groups:
                    logger.warning("⚠️ Нет групп")
                    await asyncio.sleep(self.config.get('interval', 10))
                    continue

                message = self.config.get('message_text', '')
                if not message:
                    logger.warning("⚠️ Нет текста")
                    await asyncio.sleep(self.config.get('interval', 10))
                    continue

                logger.info(f"📤 Отправка в {len(self.groups)} групп")
                success_count = 0

                for group in self.groups:
                    if not self.is_running:
                        break

                    logger.info(f"📤 Отправка в {group}...")

                    try:
                        success, error = await asyncio.wait_for(
                            self.send_to_group(group, message),
                            timeout=20
                        )
                        if success:
                            success_count += 1
                            logger.info(f"✅ Успешно в {group}")
                        else:
                            logger.error(f"❌ Ошибка в {group}: {error}")
                    except asyncio.TimeoutError:
                        logger.error(f"❌ Таймаут в {group}")

                    await asyncio.sleep(self.config.get('delay_between_groups', 3))

                logger.info(f"✅ Успешно: {success_count}/{len(self.groups)}")
                self.sent_count = 0

            except Exception as e:
                logger.error(f"❌ Ошибка цикла: {e}")
                await asyncio.sleep(5)

            if self.is_running:
                interval = self.config.get('interval', 10)
                logger.info(f"⏱ Ожидание {interval} сек")
                await asyncio.sleep(interval)

    async def start(self):
        if self.is_running:
            return

        success, error = await self._ensure_client()
        if not success:
            logger.error(f"❌ {error}")
            return

        self.is_running = True
        self.sent_count = 0
        self.last_sent_time = 0

        self.task = asyncio.create_task(self.spam_loop())
        logger.info("🚀 Рассылка запущена")

    async def stop(self):
        self.is_running = False
        self.is_paused = False

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

        if self.client and self.client.is_connected():
            await self.client.disconnect()

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
            'delay_between_groups': self.config.get('delay_between_groups', 3),
            'max_messages_per_hour': self.config.get('max_messages_per_hour', 30),
            'is_connected': self.client and self.client.is_connected() if self.client else False,
            'is_authorized': self.config.get('is_authorized', False),
            'phone': self.config.get('phone', ''),
            'auth_waiting': self._auth_waiting
        }
