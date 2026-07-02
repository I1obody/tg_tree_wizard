"""
Прогоняет TreeWizard через настоящий aiogram Dispatcher + MemoryStorage,
подставляя фейковый Bot (без реального похода в Telegram). Это позволяет
проверить весь путь — старт, выбор, назад, финал — на настоящей
инфраструктуре aiogram, не имея сетевого доступа к api.telegram.org.
"""

import sys
import os
import asyncio
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, User, Message, CallbackQuery, Update

from tg_tree_wizard.core import Node, Option
from tg_tree_wizard.aiogram_adapter import TreeWizard


TREE = {
    "lang": Node(
        text="Выберите язык:",
        options=(
            Option("Английский", "en", "delivery"),
            Option("Немецкий", "de", "delivery"),
        ),
    ),
    "delivery": Node(
        text="Выберите формат:",
        options=(
            Option("Очно", "offline", "final_confirm"),
            Option("Онлайн", "online", "final_confirm"),
        ),
    ),
    "final_confirm": Node(
        text="Подтвердите заявку:",
        options=(
            Option("Подтверждаю", "confirmed", None),
        ),
    ),
}

finished_answers = []


async def on_finish(call, state, answers):
    finished_answers.append([a.value for a in answers])
    await call.message.edit_text("Спасибо! Заявка принята.")


async def main():
    bot = Bot(token="123456:FAKE_TOKEN_NOT_REAL")
    # Подменяем реальные сетевые вызовы Telegram API моками —
    # именно тут проходит граница "не можем достучаться до api.telegram.org"
    bot.session.make_request = AsyncMock(return_value=True)

    dp = Dispatcher(storage=MemoryStorage())
    wizard = TreeWizard(TREE, root="lang", on_finish=on_finish)
    dp.include_router(wizard.router)

    user = User(id=1, is_bot=False, first_name="Тест")
    chat = Chat(id=1, type="private")

    state = dp.fsm.resolve_context(bot, chat_id=chat.id, user_id=user.id)

    # 1. Старт опроса
    fake_message = Message(
        message_id=1, date=0, chat=chat, from_user=user, text="/survey"
    ).as_(bot)
    await wizard.start(fake_message, state)
    print("[1] Старт:", (await state.get_data())["stack"])

    # 2. Выбираем "Английский" (индекс 0 на узле lang)
    call = CallbackQuery(
        id="1", from_user=user, chat_instance="x", data="wz:lang:0",
        message=Message(message_id=2, date=0, chat=chat, from_user=user, text="stub"),
    )
    call = call.model_copy(update={"bot": bot})
    await dp.feed_update(bot, Update(update_id=1, callback_query=call))
    print("[2] После выбора языка:", (await state.get_data())["stack"])

    # 3. Жмём "Назад"
    call_back = call.model_copy(update={"data": "wz_back", "id": "2"})
    await dp.feed_update(bot, Update(update_id=2, callback_query=call_back))
    print("[3] После 'Назад':", (await state.get_data())["stack"])
    print("    (должны вернуться на 'lang', answers должны быть пустыми)")
    print("    answers:", (await state.get_data())["answers"])

    # 4. Выбираем язык снова, потом формат, потом подтверждение
    await dp.feed_update(bot, Update(update_id=3, callback_query=call.model_copy(update={"id": "3"})))
    call_delivery = call.model_copy(update={"data": "wz:delivery:1", "id": "4"})
    await dp.feed_update(bot, Update(update_id=4, callback_query=call_delivery))
    print("[4] После выбора формата:", (await state.get_data())["stack"])

    call_final = call.model_copy(update={"data": "wz:final_confirm:0", "id": "5"})
    await dp.feed_update(bot, Update(update_id=5, callback_query=call_final))

    print("[5] Итоговые ответы:", finished_answers)
    print("[6] State после финала (должен быть пуст):", await state.get_data())

    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
