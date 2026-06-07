"""
bot_app/persistence.py

ConversationHandler holatlarini Django ORM da saqlaydi.
uWSGI worker qayta ishga tushganda holat yo'qolmaydi.
"""
import json
import logging
from collections import defaultdict

from asgiref.sync import sync_to_async
from telegram.ext import BasePersistence, PersistenceInput

logger = logging.getLogger(__name__)


class DjangoPersistence(BasePersistence):
    """Faqat conversation holatlarini DB ga yozadi."""

    def __init__(self):
        super().__init__(
            store_data=PersistenceInput(
                bot_data=False,
                chat_data=False,
                user_data=False,
                callback_data=False,
            )
        )

    # ── Conversation ────────────────────────────────────────────────

    async def get_conversations(self, name: str) -> dict:
        def _get():
            from bot_app.models import BotConversationState
            result = {}
            try:
                for row in BotConversationState.objects.filter(handler_name=name):
                    if row.state is not None:
                        key = tuple(json.loads(row.conv_key))
                        result[key] = row.state
            except Exception as e:
                logger.warning(f"[Persistence] get_conversations xatosi: {e}")
            return result
        return await sync_to_async(_get, thread_sensitive=False)()

    async def update_conversation(self, name: str, key, new_state) -> None:
        key_str = json.dumps(list(key))
        def _update():
            from bot_app.models import BotConversationState
            try:
                if new_state is None:
                    BotConversationState.objects.filter(
                        handler_name=name, conv_key=key_str
                    ).delete()
                else:
                    BotConversationState.objects.update_or_create(
                        handler_name=name, conv_key=key_str,
                        defaults={"state": int(new_state)},
                    )
            except Exception as e:
                logger.warning(f"[Persistence] update_conversation xatosi: {e}")
        await sync_to_async(_update, thread_sensitive=False)()

    # ── No-op metodlar (store_data=False) ──────────────────────────

    async def get_user_data(self):       return defaultdict(dict)
    async def get_chat_data(self):       return defaultdict(dict)
    async def get_bot_data(self):        return {}
    async def get_callback_data(self):   return None

    async def update_user_data(self, user_id, data):    pass
    async def update_chat_data(self, chat_id, data):    pass
    async def update_bot_data(self, data):               pass
    async def update_callback_data(self, data):          pass
    async def drop_user_data(self, user_id):             pass
    async def drop_chat_data(self, chat_id):             pass
    async def refresh_user_data(self, user_id, data):   pass
    async def refresh_chat_data(self, chat_id, data):   pass
    async def refresh_bot_data(self, bot_data):          pass
    async def flush(self):                               pass
