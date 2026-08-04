"""
Тонкий адаптер над core.py: рендер клавиатур, хендлеры aiogram,
хранение WizardState в FSMContext. Логики дерева здесь нет —
она уже проверена в core.py, тут только Telegram I/O.
"""

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .core import (
    Node, Option, DynamicOption, URLOption, SwitchOption, WizardState, choose, go_back,
    validate_tree, resolve_dynamic_options, StaleChoiceError, TreeError,
)
from .middleware import MiddlewareData, AbortWizard, MiddlewareHook


class WizardStates(StatesGroup):
    active = State()  # один State на весь опрос, независимо от глубины дерева


# Официальный лимит Telegram Bot API на длину callback_data.
TELEGRAM_CALLBACK_DATA_LIMIT_BYTES = 64


def check_callback_data_limits(tree: dict[str, Node], callback_prefix: str) -> None:
    """
    Проверяет, что callback_data ни для одного узла/варианта не превысит
    лимит Telegram в 64 байта, и что id узлов не содержат ':' (используется
    как разделитель в callback_data и сломает парсинг).

    В отличие от исходного бота, где в callback_data кодировался весь
    пройденный путь (и лимит рос вместе с глубиной дерева), здесь в
    callback_data передаётся только текущий узел + индекс варианта — путь
    хранится в FSMContext. Поэтому лимит практически не зависит от глубины
    дерева, но всё ещё зависит от длины id узлов и callback_prefix.
    """
    if ":" in callback_prefix:
        raise TreeError(f"callback_prefix {callback_prefix!r} не может содержать ':'")

    back_data = f"{callback_prefix}_back"
    back_len = len(back_data.encode("utf-8"))
    if back_len > TELEGRAM_CALLBACK_DATA_LIMIT_BYTES:
        raise TreeError(
            f"callback_data кнопки 'Назад' ({back_data!r}) занимает {back_len} байт, "
            f"это больше лимита Telegram в {TELEGRAM_CALLBACK_DATA_LIMIT_BYTES}. "
            f"Сократите callback_prefix."
        )

    for node_id, node in tree.items():
        if ":" in node_id:
            raise TreeError(
                f"id узла {node_id!r} содержит ':' — это разделитель в callback_data, "
                f"переименуйте узел."
            )

        max_index = len(node.options) - 1
        candidate = f"{callback_prefix}:{node_id}:{max_index}"
        length = len(candidate.encode("utf-8"))
        if length > TELEGRAM_CALLBACK_DATA_LIMIT_BYTES:
            raise TreeError(
                f"callback_data для узла {node_id!r} займёт {length} байт "
                f"({candidate!r}), это больше лимита Telegram в "
                f"{TELEGRAM_CALLBACK_DATA_LIMIT_BYTES}. Сократите id узла "
                f"или callback_prefix."
            )


def _visual_width(text: str) -> int:
    """
    Подсчёт визуальной ширины строки с учётом emoji (P2.3).

    Эмодзи в Telegram отображаются как двойной ширины, поэтому каждый
    символ эмодзи считается за 2 единицы ширины вместо 1.
    """
    width = 0
    for char in text:
        code_point = ord(char)
        # Основные диапазоны emoji (wide characters)
        if (
            (0x1F600 <= code_point <= 0x1F64F) or  # Emoticons
            (0x1F300 <= code_point <= 0x1F5FF) or  # Misc Symbols and Pictographs
            (0x1F680 <= code_point <= 0x1F6FF) or  # Transport and Map
            (0x1F1E0 <= code_point <= 0x1F1FF) or  # Flags
            (0x2702 <= code_point <= 0x27B0) or    # Dingbats
            (0xFE0F == code_point)                 # Variation Selector-16
        ):
            width += 2
        else:
            width += 1
    return width


def pack_buttons(
    buttons: list[InlineKeyboardButton],
    max_row_length: int = 30,
) -> list[list[InlineKeyboardButton]]:
    """
    Авто-раскладка кнопок по рядам с учётом визуальной ширины (P2.3).

    Учитывает emoji-aware ширину текста кнопок — эмодзи считаются за 2
    единицы ширины вместо 1, что точнее отражает реальное отображение
    в Telegram-клиентах.
    """
    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    current_length = 0

    for button in buttons:
        # Каждая кнопка имеет базовую ширину +5 (отступы Telegram)
        button_length = _visual_width(button.text) + 5
        if current_row and current_length + button_length > max_row_length:
            rows.append(current_row)
            current_row = [button]
            current_length = button_length
        else:
            current_row.append(button)
            current_length += button_length

    if current_row:
        rows.append(current_row)
    return rows


class TreeWizard:
    """
    Собирает Router для дерева. Использование:

        wizard = TreeWizard(TREE, root="lang", callback_prefix="wz")
        dp.include_router(wizard.router)

        @dp.message(Command("survey"))
        async def cmd_survey(message: Message, state: FSMContext):
            await wizard.start(message, state)
    """

    def __init__(
        self,
        tree: dict[str, Node],
        root: str,
        callback_prefix: str = "wz",
        max_row_length: int = 30,
        on_finish=None,  # async def on_finish(message_or_call, state, answers): ...
        on_start=None,  # async def on_start(message: Message, state: FSMContext) -> None
        middleware: list[MiddlewareHook] | None = None,
        show_cancel_button: bool = False,
        cancel_button_text: str = "❌ Отмена",
    ):
        validate_tree(tree, root)  # падаем при старте бота, а не в рантайме
        check_callback_data_limits(tree, callback_prefix)
        self.tree = tree
        self.root = root
        self.prefix = callback_prefix
        self.max_row_length = max_row_length
        self.on_finish = on_finish
        self.on_start = on_start
        self.middleware = middleware or []
        self.show_cancel_button = show_cancel_button
        self.cancel_button_text = cancel_button_text
        self.router = Router()
        self._register_handlers()

    def _build_keyboard(
        self, node_id: str, node: Node, state: WizardState | None = None
    ) -> InlineKeyboardMarkup:
        """
        Строит клавиатуру для узла. Если передан state — разворачивает
        DynamicOption в обычные Option (P1.1).
        """
        resolved_options = resolve_dynamic_options(node, state=state)

        buttons: list[InlineKeyboardButton] = []
        for i, opt in enumerate(resolved_options):
            btn_kwargs: dict[str, str | None] = {
                "text": opt.label,
                "callback_data": f"{self.prefix}:{node_id}:{i}",
            }
            if isinstance(opt, URLOption) and opt.url is not None:
                btn_kwargs["url"] = opt.url
            elif isinstance(opt, SwitchOption) and opt.switch_inline_query is not None:
                btn_kwargs["switch_inline_query"] = opt.switch_inline_query
            buttons.append(InlineKeyboardButton(**btn_kwargs))  # type: ignore[arg-type]
        rows = pack_buttons(buttons, self.max_row_length)

        # Кнопка "Назад" для не-корневых узлов
        if node_id != self.root:
            rows.append(
                [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{self.prefix}_back")]
            )

        # Кнопка "Отмена" (показывается на любом узле, если включена)
        if self.show_cancel_button:
            rows.append(
                [InlineKeyboardButton(
                    text=self.cancel_button_text,
                    callback_data=f"{self.prefix}_cancel",
                )]
            )

        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def _render(self, target, node_id: str, state: WizardState | None = None):
        """
        Рендерит узел на экран. Если передан state — разворачивает DynamicOption.
        """
        node = self.tree[node_id]
        kb = self._build_keyboard(node_id, node, state=state)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(node.text, reply_markup=kb)
        else:
            await target.answer(node.text, reply_markup=kb)

    async def start(self, message: Message, state: FSMContext):
        # Middleware hook: start
        for mw in self.middleware:
            user_id = getattr(message, "from_user", None)
            await mw(MiddlewareData(
                event_type="start", node_id=self.root,
                user_id=user_id.id if user_id else None,
            ))

        wz = WizardState.start(self.root)
        await state.set_state(WizardStates.active)
        await state.update_data(**wz.to_dict())

        # on_start hook — вызывается до отправки первого сообщения (P1.3)
        if self.on_start:
            await self.on_start(message, state)

        await self._render(message, self.root, state=wz)

    async def cancel(self, target, state: FSMContext):
        """Прерывает опрос и очищает состояние (P0.1)."""
        # Middleware hook: cancel
        user_id = None
        if isinstance(target, CallbackQuery):
            user_id = target.from_user.id
        else:
            user_id = getattr(target, "from_user", None)
            if user_id is not None:
                user_id = user_id.id

        for mw in self.middleware:
            await mw(MiddlewareData(event_type="cancel", user_id=user_id))

        await state.clear()

        text = "Диалог отменён."
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text)
        else:
            await target.answer(text)

    async def skip_to(self, target, target_node: str, state: FSMContext):
        """
        Перемещает пользователя на целевой узел, сохраняя ответы и добавляя
        узел в стек (P1.2). Полезно для /help, /menu и интеграции с другими
        хендлерами.

        target — CallbackQuery или Message для рендеринга.
        """
        # Проверяем что целевой узел существует в дереве
        if target_node not in self.tree:
            raise TreeError(f"Целевой узел {target_node!r} отсутствует в дереве")

        data = await state.get_data()
        wz = WizardState.from_dict(data)

        new_stack = wz.stack + (target_node,)
        new_wz = WizardState(stack=new_stack, answers=wz.answers)
        await state.update_data(**new_wz.to_dict())

        node = self.tree[target_node]
        kb = self._build_keyboard(target_node, node, state=new_wz)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(node.text, reply_markup=kb)
        else:
            await target.answer(node.text, reply_markup=kb)

    async def jump_to(self, target, target_node: str, state: FSMContext):
        """
        Сбрасывает стек и перемещает пользователя на целевой узел без
        сохранения пройденного пути (P1.2). Полезно для /menu — полный
        сброс к конкретному шагу.

        target — CallbackQuery или Message для рендеринга.
        """
        if target_node not in self.tree:
            raise TreeError(f"Целевой узел {target_node!r} отсутствует в дереве")

        new_wz = WizardState(stack=(target_node,), answers=())
        await state.update_data(**new_wz.to_dict())

        node = self.tree[target_node]
        kb = self._build_keyboard(target_node, node, state=new_wz)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(node.text, reply_markup=kb)
        else:
            await target.answer(node.text, reply_markup=kb)

    def _register_handlers(self):
        @self.router.callback_query(
            StateFilter(WizardStates.active), F.data.startswith(f"{self.prefix}:")
        )
        async def handle_choice(call: CallbackQuery, state: FSMContext):
            _, node_id, idx_str = call.data.split(":")
            data = await state.get_data()
            wz = WizardState.from_dict(data)

            try:
                new_wz, opt, is_final = choose(self.tree, wz, node_id, int(idx_str))
            except StaleChoiceError:
                await call.answer("Это меню устарело, начните заново.", show_alert=True)
                return

            # Middleware hook: choice
            for mw in self.middleware:
                await mw(MiddlewareData(
                    event_type="choice", node_id=node_id,
                    option_index=int(idx_str), user_id=call.from_user.id,
                ))

            await state.update_data(**new_wz.to_dict())

            if is_final:
                # Middleware hook: finish
                for mw in self.middleware:
                    await mw(MiddlewareData(
                        event_type="finish", node_id=node_id,
                        option_index=int(idx_str), user_id=call.from_user.id,
                    ))

                if self.on_finish:
                    await self.on_finish(call, state, new_wz.answers)
                await state.clear()
            else:
                await self._render(call, opt.next_node, state=new_wz)
            await call.answer()

        @self.router.callback_query(
            StateFilter(WizardStates.active), F.data == f"{self.prefix}_back"
        )
        async def handle_back(call: CallbackQuery, state: FSMContext):
            data = await state.get_data()
            wz = go_back(WizardState.from_dict(data))

            # Middleware hook: back
            for mw in self.middleware:
                await mw(MiddlewareData(
                    event_type="back", node_id=wz.current_node, user_id=call.from_user.id,
                ))

            await state.update_data(**wz.to_dict())
            await self._render(call, wz.current_node, state=wz)
            await call.answer()

        @self.router.callback_query(
            StateFilter(WizardStates.active), F.data == f"{self.prefix}_cancel"
        )
        async def handle_cancel(call: CallbackQuery, state: FSMContext):
            try:
                await self.cancel(call, state)
            except AbortWizard:
                # Middleware прервал обработку — просто подтверждаем нажатие
                await call.answer("Операция отменена.", show_alert=True)
