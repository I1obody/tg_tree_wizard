"""
Мини-проект на tg_tree_wizard: бот заказа пиццы.

Запуск:
    (в папке с установленным пакетом, venv активирован)
    pip install python-dotenv     # опционально, если хотите хранить токен в .env
    set BOT_TOKEN=ваш_токен_от_BotFather      (Windows cmd)
    $env:BOT_TOKEN="ваш_токен"                (PowerShell)
    export BOT_TOKEN=ваш_токен                (Mac/Linux)

    python pizza_bot.py

Потом в Telegram пишете боту /order и проходите дерево.
"""

import asyncio
import os
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from tg_tree_wizard import linear_wizard, TreeWizard


TREE, ROOT = linear_wizard([
    ("size", "🍕 Выберите размер пиццы:", [
        ("Маленькая (25 см)", "small"),
        ("Средняя (30 см)", "medium"),
        ("Большая (35 см)", "large"),
    ]),
    ("crust", "Выберите тесто:", [
        ("Тонкое", "thin"),
        ("Толстое", "thick"),
    ]),
    ("topping", "Выберите начинку:", [
        ("Пепперони", "pepperoni", "spicy"),   # единственная начинка с доп. вопросом
        ("Маргарита", "margherita", "confirm"),  # остальные — сразу в подтверждение
        ("Четыре сыра", "four_cheese", "confirm"),
        ("Гавайская", "hawaiian", "confirm"),
    ]),
    ("spicy", "Добавить перец чили?", [
        ("Да, поострее", "spicy_yes"),
        ("Нет, без остроты", "spicy_no"),
    ]),
    ("confirm", "Всё верно, оформляем заказ?", [
        ("✅ Подтверждаю заказ", "confirmed"),
    ]),
])

# простое "хранилище" заказов для примера — в реальном проекте тут будет
# ваш Excel/БД, как в исходном боте
ORDERS_LOG = []


async def on_finish(call: CallbackQuery, state: FSMContext, answers):
    summary = " → ".join(a.label for a in answers)
    order = {
        "user_id": call.from_user.id,
        "username": call.from_user.username,
        "summary": summary,
        "time": datetime.now().isoformat(timespec="seconds"),
    }
    ORDERS_LOG.append(order)
    print(f"[NEW ORDER] {order}")

    await call.message.edit_text(
        f"🎉 Заказ оформлен!\n\n{summary}\n\nВезём в течение 40 минут."
    )


async def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Не найден BOT_TOKEN. Установите переменную окружения с токеном от @BotFather."
        )

    bot = Bot(token=token)
    dp = Dispatcher(storage=MemoryStorage())

    wizard = TreeWizard(TREE, root=ROOT, on_finish=on_finish)
    dp.include_router(wizard.router)

    @dp.message(Command("start"))
    async def cmd_start(message: Message):
        await message.answer(
            "Привет! Я тестовый бот заказа пиццы 🍕\n"
            "Напишите /order, чтобы сделать заказ."
        )

    @dp.message(Command("order"))
    async def cmd_order(message: Message, state: FSMContext):
        await wizard.start(message, state)

    print("Бот запущен. Ctrl+C для остановки.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
