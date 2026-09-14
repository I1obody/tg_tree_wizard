"""
Telegram бот с меню, опросником и подпиской на пиццу.
Поддерживает ввод текста для регистрации.

Запуск:
    pip install -e .
    export BOT_TOKEN=ваш_токен
    python pizza_bot_text_input.py
"""

import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from tg_tree_wizard import (
    MenuOption,
    Node,
    TreeMenu,
    TreeWizard,
    linear_wizard,
)

# ==================== Состояния для регистрации ====================

class RegStates(StatesGroup):
    waiting_name = State()
    waiting_email = State()
    waiting_phone = State()


# ==================== Опросник подписки ====================

SUB_TREE, SUB_ROOT = linear_wizard([
    ("subscription", "📅 Выберите периодичность подписки на пиццу:", [
        ("Ежедневно", "daily"),
        ("Еженедельно", "weekly"),
        ("Ежемесячно", "monthly"),
    ]),
])


async def on_sub_finish(call: CallbackQuery, state: FSMContext, answers):
    """Сохраняем подписку и завершаем регистрацию."""
    data = await state.get_data()
    creds = data.get("reg_data", {})
    
    # Получаем подписку
    subscription = None
    for ans in answers:
        if ans.node == "subscription":
            subscription = ans.value
            break
    
    creds["subscription"] = subscription
    current = await state.get_data()
    current["user_credentials"] = creds
    await state.update_data(**current)
    
    text = (
        f"✅ Регистрация завершена!\n\n"
        f"Имя: {creds.get('name', 'N/A')}\n"
        f"Email: {creds.get('email', 'N/A')}\n"
        f"Телефон: {creds.get('phone', 'N/A')}\n"
        f"Подписка: {subscription}"
    )
    
    try:
        await call.message.edit_text(text)
    except Exception:
        await call.answer(text)
    
    # НЕ сбрасываем состояние, чтобы данные сохранились в FSM
    # await state.set_state(None)


sub_wizard = TreeWizard(
    SUB_TREE,
    root=SUB_ROOT,
    callback_prefix="sub",
    on_finish=on_sub_finish,
)


# ==================== Опросник пиццы ====================

PIZZA_TREE, PIZZA_ROOT = linear_wizard([
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
        ("Пепперони", "pepperoni"),
        ("Маргарита", "margherita"),
        ("Четыре сыра", "four_cheese"),
        ("Гавайская", "hawaiian"),
    ]),
    ("confirm", "Подтвердить заказ?", [
        ("✅ Подтверждаю", "confirmed"),
    ]),
])


async def on_pizza_finish(call: CallbackQuery, state: FSMContext, answers):
    """Обработка завершения заказа пиццы."""
    data = await state.get_data()
    creds = data.get("user_credentials", {})
    subscription = creds.get("subscription", "не ��казана")
    
    summary = " → ".join(a.label for a in answers)
    
    text = (
        f"🎉 Заказ оформлен!\n\n"
        f"Пользователь: {creds.get('name', 'N/A')}\n"
        f"Подписка: {subscription}\n"
        f"Заказ: {summary}\n\n"
        f"Доставим согласно вашей подписке!"
    )
    
    try:
        await call.message.edit_text(text)
    except Exception:
        await call.answer(text)


pizza_wizard = TreeWizard(
    PIZZA_TREE,
    root=PIZZA_ROOT,
    callback_prefix="pizza",
    on_finish=on_pizza_finish,
)


# ==================== Главное меню ====================

MENU_TREE = {
    "main": Node(
        text=lambda state: (
            "🏠 Главное меню\n\n"
            f"👤 {state.data.get('user_credentials', {}).get('name', 'Гость')}\n"
            f"📧 {state.data.get('user_credentials', {}).get('email', 'Не указано')}\n"
            f"📱 {state.data.get('user_credentials', {}).get('phone', 'Не указано')}\n"
            f"📅 Подписка: {state.data.get('user_credentials', {}).get('subscription', 'Не указана')}"
        ),
        options=(
            MenuOption(label="👤 Мои данные", value="credentials", next_node="credentials"),
            MenuOption(label="📋 Опрос пиццы", value="pizza_survey", next_node="pizza_survey"),
            MenuOption(label="🔄 Изменить подписку", value="change_sub", next_node="change_sub"),
            MenuOption(label="📝 Регистрация", value="register", next_node="register"),
        ),
    ),
    "credentials": Node(
        text=lambda state: (
            "👤 Ваши данные\n\n"
            f"Имя: {state.data.get('user_credentials', {}).get('name', 'Не указано')}\n"
            f"Email: {state.data.get('user_credentials', {}).get('email', 'Не указано')}\n"
            f"Телефон: {state.data.get('user_credentials', {}).get('phone', 'Не указано')}\n"
            f"Подписка: {state.data.get('user_credentials', {}).get('subscription', 'Не указана')}"
            if state.data.get('user_credentials')
            else "⚠️ Вы еще не зарегистрированы"
        ),
        options=(
            MenuOption(label="📝 Редактировать", value="edit", next_node="register"),
        ),
    ),
    "pizza_survey": Node(
        text="🍕 Опрос пиццы",
        options=(
            MenuOption(label="🚀 Начать опрос", value="start_pizza", callback_data="pizza_start"),
        ),
    ),
    "change_sub": Node(
        text="🔄 Изменение подписки",
        options=(
            MenuOption(label="Ежедневно", value="daily", callback_data="sub_daily"),
            MenuOption(label="Еженедельно", value="weekly", callback_data="sub_weekly"),
            MenuOption(label="Ежемесячно", value="monthly", callback_data="sub_monthly"),
        ),
    ),
    "register": Node(
        text="📝 Регистрация",
        options=(
            MenuOption(label="🚀 Начать регистрацию", value="start_reg", callback_data="reg_start"),
        ),
    ),
}


menu = TreeMenu(
    MENU_TREE,
    root="main",
    callback_prefix="menu",
)


# ==================== Обработчики регистрации с вводом текста ====================

async def start_registration(message: Message, state: FSMContext):
    """Запуск регистрации с вводом текста."""
    await state.set_state(RegStates.waiting_name)
    await state.update_data(reg_data={})
    await message.answer("👤 Введите ваше имя:")


async def show_credentials(message: Message, state: FSMContext):
    """Показывает данные пользователя."""
    data = await state.get_data()
    creds = data.get("user_credentials", {})
    
    if not creds:
        await message.answer("⚠️ Вы еще не зарегистрированы. Используйте /register")
        return
    
    text = (
        f"👤 Ваши данные:\n\n"
        f"Имя: {creds.get('name', 'Не указано')}\n"
        f"Email: {creds.get('email', 'Не указано')}\n"
        f"Телефон: {creds.get('phone', 'Не указано')}\n"
        f"Подписка: {creds.get('subscription', 'Не указана')}"
    )
    await message.answer(text)


async def handle_name(message: Message, state: FSMContext):
    """Обработка ввода имени."""
    if not message.text:
        await message.answer("Пожалуйста, введите имя")
        return
    name = message.text.strip()
    data = await state.get_data()
    reg_data = data.get("reg_data", {})
    reg_data["name"] = name
    await state.update_data(reg_data=reg_data)
    await state.set_state(RegStates.waiting_email)
    await message.answer("📧 Введите ваш email:")


async def handle_email(message: Message, state: FSMContext):
    """Обработка ввода email."""
    if not message.text:
        await message.answer("Пожалуйста, введите email")
        return
    email = message.text.strip()
    data = await state.get_data()
    reg_data = data.get("reg_data", {})
    reg_data["email"] = email
    await state.update_data(reg_data=reg_data)
    await state.set_state(RegStates.waiting_phone)
    await message.answer("📱 Введите ваш телефон:")


async def handle_phone(message: Message, state: FSMContext):
    """Обработка ввода телефона и переход к выбору подписки."""
    if not message.text:
        await message.answer("Пожалуйста, введите телефон")
        return
    phone = message.text.strip()
    data = await state.get_data()
    reg_data = data.get("reg_data", {})
    reg_data["phone"] = phone
    await state.update_data(reg_data=reg_data)
    
    await message.answer(
        f"✅ Данные сохранены:\n"
        f"Имя: {reg_data['name']}\n"
        f"Email: {reg_data['email']}\n"
        f"Телефон: {reg_data['phone']}\n\n"
        f"Теперь выберите периодичность подписки:"
    )
    
    # Запускаем выбор подписки через TreeWizard
    await sub_wizard.start(message, state)


# ==================== Обработчики кастомных callback ====================

async def handle_custom_callbacks(call: CallbackQuery, state: FSMContext):
    """Обработка кастомных callback_data из меню."""
    data = call.data
    
    if not data:
        await call.answer("Неизвестная команда")
        return
    
    if data == "pizza_start":
        await pizza_wizard.start(call, state)
    elif data == "reg_start":
        # Запускаем регистрацию с вводом текста
        if call.message:
            await start_registration(call.message, state)
        else:
            await call.answer("Ошибка запуска регистрации")
        return
    elif data.startswith("sub_"):
        # Обновляем подписку
        sub_type = data.split("_")[1]
        current = await state.get_data()
        creds = current.get("user_credentials", {})
        creds["subscription"] = sub_type
        current["user_credentials"] = creds
        await state.update_data(**current)
        
        text = (
            f"✅ Подписка изменена на: {sub_type}\n\n"
            f"Теперь опросы будут приходить {sub_type}."
        )
        
        try:
            await call.message.edit_text(text)
        except Exception:
            await call.answer(text)
    else:
        await call.answer("Неизвестная команда")


# ==================== Основной бот ====================

async def main():
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Не найден BOT_TOKEN")
    
    bot = Bot(token=token)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрируем роутеры
    dp.include_router(menu.router)
    dp.include_router(sub_wizard.router)
    dp.include_router(pizza_wizard.router)
    
    # Обработчики регистрации с вводом текста
    dp.message.register(start_registration, Command("register_text"))
    dp.message.register(handle_name, StateFilter(RegStates.waiting_name))
    dp.message.register(handle_email, StateFilter(RegStates.waiting_email))
    dp.message.register(handle_phone, StateFilter(RegStates.waiting_phone))
    
    # Обработчик кастомных callback
    dp.callback_query.register(handle_custom_callbacks, F.data.in_([
        "pizza_start", "reg_start", "sub_daily", "sub_weekly", "sub_monthly"
    ]))
    
    @dp.message(Command("start"))
    async def cmd_start(message: Message, state: FSMContext):
        await message.answer(
            "🍕 Добро пожаловать в Pizza Bot!\n\n"
            "Используйте /menu для открытия меню.\n"
            "Сначала пройдите регистрацию для сохранения данных."
        )
    
    @dp.message(Command("menu"))
    async def cmd_menu(message: Message, state: FSMContext):
        await menu.start(message, state)
    
    @dp.message(Command("register"))
    async def cmd_register(message: Message, state: FSMContext):
        await start_registration(message, state)
    
    @dp.message(Command("pizza"))
    async def cmd_pizza(message: Message, state: FSMContext):
        await pizza_wizard.start(message, state)
    
    @dp.message(Command("mydata"))
    async def cmd_mydata(message: Message, state: FSMContext):
        await show_credentials(message, state)
    
    print("Бот запущен. Команды: /start, /menu, /register, /pizza")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
