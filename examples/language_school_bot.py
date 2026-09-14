"""
Реальный пример: тот же опрос, что был у вас в main.py, но описан данными
через tg_tree_wizard, а не 6 отдельными хендлерами.

Запуск:
    pip install -e .           # из корня пакета, один раз
    export BOT_TOKEN=...       # ваш настоящий токен
    python examples/language_school_bot.py
"""

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery

from tg_tree_wizard import Node, Option, TreeWizard

TREE = {
    "lang": Node(
        text="Выберите язык:",
        options=(
            Option("Английский", "en", "delivery"),
            Option("Китайский", "cn", "delivery"),
            Option("Немецкий", "de", "delivery"),
            Option("Французский", "fr", "delivery"),
            Option("Испанский", "es", "delivery"),
        ),
    ),
    "delivery": Node(
        text="Выберите формат занятий:",
        options=(
            Option("Очно", "offline", "goal"),
            Option("Онлайн", "online", "goal"),
        ),
    ),
    "goal": Node(
        text="Выберите цель обучения:",
        options=(
            Option("Для школы", "school", "group"),
            Option("Для работы", "work", "group"),
            Option("Переезд в другую страну", "relocation", "group"),
        ),
    ),
    "group": Node(
        text="Индивидуально или в группе?",
        options=(
            Option("Индивидуальный", "solo", None),
            Option("Группа", "group", None),
        ),
    ),
}


async def on_finish(call: CallbackQuery, state: FSMContext, answers):
    summary = ", ".join(a.label for a in answers)
    await call.message.edit_text(f"Спасибо! Ваша заявка: {summary}")
    # здесь — ваша логика записи в Excel / отправки админу, как в исходном боте


async def main():
    bot = Bot(token=os.environ["BOT_TOKEN"])
    dp = Dispatcher(storage=MemoryStorage())

    wizard = TreeWizard(TREE, root="lang", on_finish=on_finish)
    dp.include_router(wizard.router)

    @dp.message(Command("survey"))
    async def cmd_survey(message, state: FSMContext):
        await wizard.start(message, state)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
