import asyncio
import json
import logging
import time
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from telethon import TelegramClient, errors
from telethon.tl.types import Message

# СОЗДАЕМ ПАПКУ ДЛЯ ЛОГОВ ДО НАСТРОЙКИ
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
        self._last_sent_code_time = 0

        # Проверяем и создаем файлы
        self.ensure_files()
        self.load_config()
        self.load_groups()

    def ensure_files(self):
        """Проверка и создание необходимых файлов"""
        os.makedirs('logs', exist_ok=True)

        if not os.path.exists(self.config_file):
            default_config = {
                "api_id": 0,
                "api_hash": "",
                "session_name": "spammer_session",
                "phone": "",
                "message_text": "🔥 Привет! Подписывайся на мой канал: https://t.me/my_channel\n\nТут ты найдешь:\n- Полезный контент\n- Новости\n- Эксклюзив",
                "interval": 3600,
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
        """Загрузка конфигурации"""
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
                "message_text": "🔥 Привет! Подписывайся на мой канал: https://t.me/my_channel",
                "interval": 3600,
                "delay_between_groups": 3,
                "max_messages_per_hour": 30,
                "enabled": False,
                "is_authorized": False
            }
            self.save_config()

    def save_config(self):
        """Сохранение конфигурации"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения конфига: {e}")

    def load_groups(self):
        """Загрузка списка групп"""
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
        """Сохранение списка групп"""
        try:
            with open(self.groups_file, 'w', encoding='utf-8') as f:
                json.dump(self.groups, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения групп: {e}")

    async def send_auth_code(self, phone: str) -> Tuple[bool, str]:
        """Отправить код подтверждения на телефон"""
        try:
            self._auth_phone = phone
            self._auth_waiting = True

            # Проверяем API данные
            if not self.config.get('api_id') or not self.config.get('api_hash'):
                return False, "API ID или API Hash не указаны!"

            # Создаем клиент если нужно
            if not self.client:
                self.client = TelegramClient(
                    self.config['session_name'],
                    self.config['api_id'],
                    self.config['api_hash']
                )

            # Подключаемся
            if not self.client.is_connected():
                await self.client.connect()
                logger.info("✅ Клиент подключен")

            # Проверяем авторизацию
            if await self.client.is_user_authorized():
                self.config['is_authorized'] = True
                self.config['phone'] = phone
                self.save_config()
                self._auth_waiting = False
                return True, "Уже авторизован"

            # Отправляем запрос на код
            try:
                # Проверяем, не отправляли ли мы код недавно
                current_time = time.time()
                if current_time - self._last_sent_code_time < 30:
                    return False, "Код уже был отправлен. Подождите 30 секунд или введите полученный код."

                result = await self.client.send_code_request(phone)

                # Сохраняем phone_code_hash
                if hasattr(result, 'phone_code_hash'):
                    self._auth_phone_code_hash = result.phone_code_hash
                else:
                    self._auth_phone_code_hash = result.phone_code_hash

                self._last_sent_code_time = current_time
                logger.info(f"✅ Код отправлен на {phone}")
                return True, "Код подтверждения отправлен на ваш номер"

            except errors.PhoneNumberInvalidError:
                return False, "Неверный номер телефона"
            except errors.FloodWaitError as e:
                return False, f"Слишком много попыток. Подождите {e.seconds} секунд"
            except errors.PhoneCodeHashInvalidError:
                logger.warning("⚠️ PhoneCodeHash устарел, пробуем отправить заново")
                result = await self.client.send_code_request(phone)
                self._auth_phone_code_hash = result.phone_code_hash
                return True, "Код подтверждения отправлен повторно"

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Ошибка отправки кода: {error_msg}")

            if "ResendCodeRequest" in error_msg or "already used" in error_msg:
                try:
                    logger.info("🔄 Пробуем отправить код через новый клиент...")
                    if self.client:
                        await self.client.disconnect()

                    self.client = TelegramClient(
                        f"{self.config['session_name']}_new",
                        self.config['api_id'],
                        self.config['api_hash']
                    )
                    await self.client.connect()

                    result = await self.client.send_code_request(phone)
                    if hasattr(result, 'phone_code_hash'):
                        self._auth_phone_code_hash = result.phone_code_hash
                    else:
                        self._auth_phone_code_hash = result.phone_code_hash

                    self._last_sent_code_time = time.time()
                    logger.info(f"✅ Код отправлен на {phone} через новый запрос")
                    return True, "Код подтверждения отправлен на ваш номер"
                except Exception as e2:
                    logger.error(f"❌ Ошибка повторной отправки: {e2}")
                    return False, f"Ошибка отправки кода. Попробуйте перезапустить приложение. Ошибка: {str(e2)}"

            return False, f"Ошибка: {error_msg}"

    async def verify_auth_code(self, code: str) -> Tuple[bool, str]:
        """Подтвердить код авторизации"""
        try:
            if not self.client:
                return False, "Клиент не инициализирован. Сначала отправьте код"

            if not self._auth_phone_code_hash:
                return False, "Сначала запросите код подтверждения"

            if not self.client.is_connected():
                await self.client.connect()

            try:
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
                return True, "Авторизация успешна! Теперь можно запускать рассылку."

            except errors.SessionPasswordNeededError:
                return False, "Требуется двухфакторная аутентификация (2FA). Пока не поддерживается"
            except errors.PhoneCodeInvalidError:
                return False, "Неверный код подтверждения. Попробуйте еще раз"
            except errors.PhoneCodeExpiredError:
                return False, "Код истек. Запросите новый код"
            except errors.PhoneNumberInvalidError:
                return False, "Неверный номер телефона"
            except errors.PhoneCodeHashInvalidError:
                return False, "Код устарел. Запросите новый код"

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Ошибка подтверждения кода: {error_msg}")

            if "PhoneCodeInvalid" in error_msg or "PhoneCodeExpired" in error_msg:
                return False, f"Ошибка: {error_msg}. Запросите новый код"

            return False, f"Ошибка: {error_msg}"

    async def _ensure_client(self) -> Tuple[bool, str]:
        """Гарантирует, что клиент инициализирован и подключен"""
        async with self._client_lock:
            try:
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

                if not await self.client.is_user_authorized():
                    if self.config.get('phone'):
                        try:
                            await self.client.start(phone=self.config['phone'])
                            self.config['is_authorized'] = True
                            self.save_config()
                            logger.info("✅ Авторизован по сохраненной сессии")
                        except Exception as e:
                            return False, f"Требуется авторизация. Ошибка: {str(e)}"
                    else:
                        return False, "Требуется авторизация. Используйте /api/auth/send для отправки кода"

                return True, "OK"

            except Exception as e:
                error_msg = f"Ошибка подключения клиента: {str(e)}"
                logger.error(f"❌ {error_msg}")
                return False, error_msg

    async def _get_client(self):
        """Получить клиента (с проверкой подключения)"""
        success, error = await self._ensure_client()
        if not success:
            raise Exception(error)
        return self.client

    async def get_entity_by_id(self, entity_id):
        """Получение сущности по ID с обработкой ошибок"""
        try:
            client = await self._get_client()

            if isinstance(entity_id, str) and entity_id.startswith('-100'):
                return await client.get_entity(int(entity_id))
            elif isinstance(entity_id, str) and entity_id.isdigit():
                return await client.get_entity(int(entity_id))
            elif isinstance(entity_id, str) and entity_id.startswith('@'):
                return await client.get_entity(entity_id)
            else:
                return await client.get_entity(entity_id)

        except ValueError as e:
            raise Exception(f"Не удалось найти сущность: {str(e)}")
        except errors.FloodWaitError as e:
            raise Exception(f"FloodWait: ждите {e.seconds} секунд")
        except Exception as e:
            raise Exception(f"Ошибка получения сущности: {str(e)}")

    async def send_to_group(self, group: str, message: str) -> Tuple[bool, str]:
        """Отправка сообщения в группу. Возвращает (успех, сообщение_об_ошибке)"""
        try:
            client = await self._get_client()

            max_msgs = self.config.get('max_messages_per_hour', 30)
            if self.sent_count >= max_msgs:
                msg = f"Достигнут лимит сообщений в час ({max_msgs})"
                logger.warning(f"⚠️ {msg}")
                return False, msg

            current_time = time.time()
            delay = self.config.get('delay_between_groups', 3)
            if current_time - self.last_sent_time < delay:
                wait_time = delay - (current_time - self.last_sent_time)
                await asyncio.sleep(wait_time)

            try:
                entity = await self.get_entity_by_id(group)
                logger.info(f"🔍 Получена сущность для {group}")
            except Exception as e:
                return False, f"Группа не найдена: {str(e)}"

            try:
                await client.send_message(entity, message)
                logger.info(f"✅ Отправлено в {group}")
            except errors.ChatWriteForbiddenError:
                return False, "Нет прав на отправку сообщений в эту группу"
            except errors.RPCError as e:
                return False, f"Ошибка Telegram: {str(e)}"

            self.sent_count += 1
            self.last_sent_time = time.time()

            return True, "OK"

        except errors.FloodWaitError as e:
            wait = e.seconds
            msg = f"FloodWait: ждём {wait} секунд"
            logger.warning(f"⚠️ {msg}")
            await asyncio.sleep(wait)
            return False, msg
        except asyncio.CancelledError:
            return False, "Операция отменена"
        except Exception as e:
            error_msg = f"Неизвестная ошибка: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return False, error_msg

    async def spam_loop(self):
        """Основной цикл рассылки"""
        logger.info("🔄 Запуск цикла рассылки")

        while self.is_running:
            try:
                if self.is_paused:
                    await asyncio.sleep(5)
                    continue

                if not self.config.get('enabled', False):
                    logger.info("⏸️ Рассылка отключена в настройках")
                    await asyncio.sleep(self.config.get('interval', 3600))
                    continue

                if not self.groups:
                    logger.warning("⚠️ Нет групп для рассылки")
                    await asyncio.sleep(self.config.get('interval', 3600))
                    continue

                message = self.config.get('message_text', '')
                if not message:
                    logger.warning("⚠️ Текст сообщения не указан!")
                    await asyncio.sleep(self.config.get('interval', 3600))
                    continue

                logger.info(f"📤 Отправка в {len(self.groups)} групп")
                success_count = 0
                error_messages = []

                for group in self.groups:
                    if not self.is_running:
                        break

                    success, error_msg = await self.send_to_group(group, message)
                    if success:
                        success_count += 1
                    else:
                        error_messages.append(f"{group}: {error_msg}")

                    await asyncio.sleep(self.config.get('delay_between_groups', 3))

                logger.info(f"✅ Успешно: {success_count}/{len(self.groups)}")
                if error_messages:
                    logger.warning(f"⚠️ Ошибки: {', '.join(error_messages[:5])}")

                self.sent_count = 0

            except Exception as e:
                logger.error(f"❌ Ошибка в цикле рассылки: {e}")
                await asyncio.sleep(5)

            if self.is_running:
                interval = self.config.get('interval', 3600)
                logger.info(f"⏱ Ожидание {interval} секунд")
                await asyncio.sleep(interval)

    async def start(self):
        """Запуск рассылки"""
        if self.is_running:
            logger.warning("⚠️ Рассылка уже запущена")
            return

        try:
            success, error = await self._ensure_client()
            if not success:
                logger.error(f"❌ {error}")
                return

            if not self.config.get('message_text'):
                logger.error("❌ Текст сообщения не указан!")
                return

            self.is_running = True
            self.sent_count = 0
            self.last_sent_time = 0

            self.task = asyncio.create_task(self.spam_loop())
            logger.info("🚀 Рассылка запущена")

        except Exception as e:
            logger.error(f"❌ Ошибка запуска: {e}")
            self.is_running = False

    async def stop(self):
        """Остановка рассылки"""
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

        logger.info("🛑 Рассылка остановлена")

    def pause(self):
        self.is_paused = True
        logger.info("⏸️ Пауза")

    def resume(self):
        self.is_paused = False
        logger.info("▶️ Продолжено")

    def get_status(self) -> Dict:
        is_authorized = self.config.get('is_authorized', False)
        if self.client and self.client.is_connected():
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                is_authorized = loop.run_until_complete(self.client.is_user_authorized())
                loop.close()
            except:
                pass

        return {
            'running': self.is_running,
            'paused': self.is_paused,
            'groups_count': len(self.groups),
            'groups': self.groups,
            'message_text': self.config.get('message_text', ''),
            'interval': self.config.get('interval', 3600),
            'enabled': self.config.get('enabled', False),
            'delay_between_groups': self.config.get('delay_between_groups', 3),
            'max_messages_per_hour': self.config.get('max_messages_per_hour', 30),
            'is_connected': self.client and self.client.is_connected() if self.client else False,
            'is_authorized': is_authorized,
            'phone': self.config.get('phone', ''),
            'auth_waiting': self._auth_waiting
        }
