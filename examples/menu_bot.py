"""
Пример меню для Telegram бота с использованием tg-tree_wizard.

Запуск:
    pip install python-dotenv     # опционально, если хотите хранить токен в .env
    set BOT_TOKEN=ваш_токен_от_BotFather      (Windows cmd)
    $env:BOT_TOKEN="ваш_токен"                (PowerShell)
    export BOT_TOKEN=ваш_токен                (Mac/Linux)

    python menu_bot.py

После запуска в Telegram пишете боту /menu и переходите по меню.
"""

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from tg_tree_wizard import TreeMenu, MenuOption, Node


# Дерево меню — нелинейная навигация с помощью MenuOption.
MENU_TREE = {
    "main": Node(
        text="🏠 Главное меню",
        options=(
            MenuOption(label="📋 Мои заказы", value="orders", next_node="orders"),
            MenuOption(label="ℹ️ О нас", value="about", next_node="about"),
            MenuOption(label="👤 Профиль", value="profile", next_node="profile"),
            MenuOption(label="⚙️ Настройки", value="settings", next_node="settings"),
        ),
    ),
    "orders": Node(
        text="📋 Ваши заказы:",
        options=(
            MenuOption(label="🟢 Активные", value="active_orders"),
            MenuOption(label="✅ Завершённые", value="completed_orders"),
            MenuOption(label="⬅️ Назад в меню", value=None, next_node="main"),
        ),
    ),
    "about": Node(
        text="ℹ️ О нашем боте:\n\nМы — команда разработчиков, создающая лучшие Telegram-боты.",
        options=(
            MenuOption(label="👥 Команда", value="team"),
            MenuOption(label="📞 Контакты", value="contacts"),
            MenuOption(label="⬅️ Назад в меню", value=None, next_node="main"),
        ),
    ),
    "profile": Node(
        text="👤 Ваш профиль:\n\nИмя: Иван Иванов\nГород: Москва",
        options=(
            MenuOption(label="✏️ Редактировать", value="edit_profile"),
            MenuOption(label="⬅️ Назад в меню", value=None, next_node="main"),
        ),
    ),
    "settings": Node(
        text="⚙️ Настройки:",
        options=(
            MenuOption(label="🔔 Уведомления", value="notifications"),
            MenuOption(label="🌐 Язык", value="language"),
            MenuOption(label="🎨 Тема", value="theme"),
            MenuOption(label="⬅️ Назад в меню", value=None, next_node="main"),
        ),
    ),
}


async def on_menu_start(message: Message, state: FSMContext):
    """Вызывается при каждом запуске меню."""
    print(f"[Menu] Start for user {message.from_user.id}")


async def on_menu_choice(data):
    """Middleware hook для выбора опции меню."""
    print(f"[Menu] Choice: node={data.node_id}, index={data.option_index}")


async def on_menu_finish(call: CallbackQuery, state: FSMContext, menu_data: dict):
    """Вызывается при завершении работы с меню (next_node=None)."""
    print(f"[Menu] Finish for user {call.from_user.id}, data: {menu_data}")


# Создаём TreeMenu глобально, чтобы он был доступен из cmd_menu()
menu = TreeMenu(
    tree=MENU_TREE,
    root="main",
    callback_prefix="menu",
    on_start=on_menu_start,
    on_finish=on_menu_finish,
    middleware=[on_menu_choice],
)


async def cmd_menu(message: Message, state: FSMContext):
    """Обработчик команды /menu — запускает главное меню."""
    await menu.start(message, state)


async def main():
    bot = Bot(token=os.environ.get("BOT_TOKEN", "your_bot_token"))
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.include_router(menu.router)

    @dp.message(Command("menu"))
    async def cmd_handler(message: Message, state: FSMContext):
        await cmd_menu(message, state)

    print("Бот запущен. Отправьте /menu для открытия меню.")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот остановлен.")
