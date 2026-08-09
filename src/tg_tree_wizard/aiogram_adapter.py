"""
Тонкий адаптер над core.py: рендер клавиатур, хендлеры aiogram,
хранение WizardState в FSMContext. Логики дерева здесь нет —
она уже проверена в core.py, тут только Telegram I/O.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .core import (
    MenuOption,
    MenuState,
    Node,
    StaleChoiceError,
    SwitchOption,
    TreeError,
    URLOption,
    WizardState,
    choose,
    go_back,
    resolve_dynamic_options,
    validate_tree,
)
from .middleware import (
    AbortWizard,
    MenuAbortWizard,
    MenuMiddlewareData,
    MenuMiddlewareHook,
    MiddlewareData,
    MiddlewareHook,
)


class WizardStates(StatesGroup):
    active = State()  # один State на весь опрос, независимо от глубины дерева


class QuizStates(StatesGroup):
    active = State()  # состояние для квиза (отдельное от survey)


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
            (0x1F600 <= code_point <= 0x1F64F)  # Emoticons
            or (0x1F300 <= code_point <= 0x1F5FF)  # Misc Symbols and Pictographs
            or (0x1F680 <= code_point <= 0x1F6FF)  # Transport and Map
            or (0x1F1E0 <= code_point <= 0x1F1FF)  # Flags
            or (0x2702 <= code_point <= 0x27B0)  # Dingbats
            or (0xFE0F == code_point)  # Variation Selector-16
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
        back_button_text: str = "⬅️ Назад",
        state_group: type[StatesGroup] | None = None,
    ):
        validate_tree(
            tree, root, allow_external_refs=True
        )  # TreeWizard допускает внешние ссылки (main_menu)
        check_callback_data_limits(tree, callback_prefix)
        # Если state_group не передан — используем WizardStates по умолчанию
        if state_group is None:
            state_group = WizardStates
        self.tree = tree
        self.root = root
        self.prefix = callback_prefix
        self.max_row_length = max_row_length
        self.on_finish = on_finish
        self.on_start = on_start
        self.middleware = middleware or []
        self.show_cancel_button = show_cancel_button
        self.cancel_button_text = cancel_button_text
        self.back_button_text = back_button_text
        self.router = Router()
        self.state_group = state_group
        self._register_handlers()

    def _build_keyboard(
        self, node_id: str, node: Node, state: WizardState | None = None
    ) -> InlineKeyboardMarkup:
        """
        Строит клавиатуру для узла. Если передан state — разворачивает
        DynamicOption в обычные Option (P1.1).

        Поддерживает кастомный callback_data для MenuOption (как и TreeMenu._build_menu_keyboard).
        """
        resolved_options = resolve_dynamic_options(node, state=state)

        buttons: list[InlineKeyboardButton] = []
        for i, opt in enumerate(resolved_options):
            # Если у MenuOption задан кастомный callback_data — используем его
            if isinstance(opt, MenuOption) and opt.callback_data is not None:
                cb_data = opt.callback_data
            else:
                cb_data = f"{self.prefix}:{node_id}:{i}"

            btn_kwargs: dict[str, str | None] = {
                "text": opt.label,
                "callback_data": cb_data,
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
                [
                    InlineKeyboardButton(
                        text=self.back_button_text, callback_data=f"{self.prefix}_back"
                    )
                ]
            )

        # Кнопка "Отмена" (показывается на любом узле, если включена)
        if self.show_cancel_button:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=self.cancel_button_text,
                        callback_data=f"{self.prefix}_cancel",
                    )
                ]
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

    async def start(self, target: Message | CallbackQuery, state: FSMContext):
        """Запускает wizard с корневого узла. target — Message или CallbackQuery."""
        user_id = getattr(target, "from_user", None)
        print(
            f"[TREE_WIZARD_START] root={self.root} user_id={getattr(user_id, 'id', None)}"
        )
        # Middleware hook: start
        for mw in self.middleware:
            uid = getattr(user_id, "id", None) if user_id else None
            await mw(
                MiddlewareData(
                    event_type="start",
                    node_id=self.root,
                    user_id=uid,
                )
            )

        wz = WizardState.start(self.root)
        print(
            f"[TREE_WIZARD_START] Setting state to {self.state_group.__name__}.active, root={self.root}"
        )
        await state.set_state(self.state_group.active)
        await state.update_data(**wz.to_dict())

        # on_start hook — вызывается до отправки первого сообщения (P1.3)
        if self.on_start:
            print("[TREE_WIZARD_START] Calling on_start hook")
            await self.on_start(target, state)

        print(f"[TREE_WIZARD_START] Rendering root node={self.root}")
        await self._render(target, self.root, state=wz)

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

    async def switch_to_menu(
        self,
        state: FSMContext,
        target,
        target_node: str | None = None,
        shared_data: dict | None = None,
        menu: TreeMenu | None = None,
    ):
        """
        Переводит пользователя из опроса в меню (P2).

        Если target_node не указан — переходит на корневой узел меню.
        shared_data передаётся в middleware и сохраняется для дальнейшего использования.

        target — CallbackQuery или Message для рендеринга.
        menu — TreeMenu, чьё дерево используется для рендеринга (обязательно при вызове из Wizard).
               Если не передан, используется self.tree (для случаев когда self уже является меню).
        """
        # Middleware hook: transition_to_menu
        user_id = None
        if isinstance(target, CallbackQuery):
            user_id = target.from_user.id
        else:
            user_id = getattr(target, "from_user", None)
            if user_id is not None:
                user_id = user_id.id

        for mw in self.middleware:
            await mw(
                MiddlewareData(
                    event_type="transition_to_menu",
                    user_id=user_id,
                    target_node=target_node,
                    shared_data=shared_data or {},
                )
            )

        # Сохраняем shared_data в FSMContext
        if shared_data:
            current_data = await state.get_data()
            current_data["shared_data"] = shared_data
            await state.update_data(**current_data)

        # Переключаемся на MenuStates.active
        await state.set_state(MenuStates.active)

        # Если target_node не указан, используем корневой узел меню (предполагаем "main")
        if target_node is None:
            target_node = "main"

        ms = MenuState(current_node=target_node, parent_node=None)

        # ВАЖНО: НЕ перезаписываем существующие данные FSM (язык, баллы квиза и т.д.)
        # Вместо этого обновляем только поля MenuState поверх существующих данных
        current_data = await state.get_data()
        merged_data = {**current_data, **ms.to_dict()}
        await state.update_data(**merged_data)

        # ВАЖНО: при вызове из Wizard self.tree — это дерево опроса, а не меню.
        # Нужно использовать menu.tree для рендеринга узлов главного меню.
        if menu is not None:
            node = menu.tree[target_node]
            kb = menu._build_menu_keyboard(target_node, node, state=ms)
        else:
            node = self.tree[target_node]
            kb = self._build_menu_keyboard(target_node, node, state=ms)

        if isinstance(target, CallbackQuery):
            await target.message.edit_text(node.text, reply_markup=kb)
        else:
            await target.answer(node.text, reply_markup=kb)

    def _register_handlers(self):
        state_filter = (
            self.state_group.active
            if hasattr(self, "state_group")
            else WizardStates.active
        )

        @self.router.callback_query(
            StateFilter(state_filter), F.data.startswith(f"{self.prefix}:")
        )
        async def handle_choice(call: CallbackQuery, state: FSMContext):
            print(
                f"[TREE_WIZARD_CHOICE] call.data={call.data} user_id={call.from_user.id}"
            )
            _, node_id, idx_str = call.data.split(":")
            data = await state.get_data()
            wz = WizardState.from_dict(data)
            print(
                f"[TREE_WIZARD_CHOICE] Parsed: node_id={node_id}, idx_str={idx_str}, current_node={wz.current_node}"
            )

            try:
                new_wz, opt, is_final = choose(self.tree, wz, node_id, int(idx_str))
                print(
                    f"[TREE_WIZARD_CHOICE] Chose option: label={opt.label!r} value={opt.value!r} next_node={opt.next_node} is_final={is_final}"
                )
            except StaleChoiceError as e:
                print(f"[TREE_WIZARD_CHOICE] StaleChoiceError: {e}")
                await call.answer("Это меню устарело, начните заново.", show_alert=True)
                return

            # Middleware hook: choice
            for mw in self.middleware:
                await mw(
                    MiddlewareData(
                        event_type="choice",
                        node_id=node_id,
                        option_index=int(idx_str),
                        user_id=call.from_user.id,
                    )
                )

            await state.update_data(**new_wz.to_dict())

            if is_final:
                print("[TREE_WIZARD_CHOICE] Final step reached! Calling on_finish")
                # Middleware hook: finish
                for mw in self.middleware:
                    await mw(
                        MiddlewareData(
                            event_type="finish",
                            node_id=node_id,
                            option_index=int(idx_str),
                            user_id=call.from_user.id,
                        )
                    )

                if self.on_finish:
                    print("[TREE_WIZARD_CHOICE] Calling on_finish handler")
                    await self.on_finish(call, state, new_wz.answers)
                print("[TREE_WIZARD_CHOICE] Clearing FSM state after finish")
                await state.clear()
            else:
                print(f"[TREE_WIZARD_CHOICE] Rendering next node={opt.next_node}")
                await self._render(call, opt.next_node, state=new_wz)
            await call.answer()

        @self.router.callback_query(
            StateFilter(state_filter), F.data == f"{self.prefix}_back"
        )
        async def handle_back(call: CallbackQuery, state: FSMContext):
            print(
                f"[TREE_WIZARD_BACK] call.data={call.data} user_id={call.from_user.id}"
            )
            data = await state.get_data()
            wz = go_back(WizardState.from_dict(data))
            print(
                f"[TREE_WIZARD_BACK] After go_back: current_node={wz.current_node}, stack={wz.stack}"
            )

            # Middleware hook: back
            for mw in self.middleware:
                await mw(
                    MiddlewareData(
                        event_type="back",
                        node_id=wz.current_node,
                        user_id=call.from_user.id,
                    )
                )

            await state.update_data(**wz.to_dict())
            print(f"[TREE_WIZARD_BACK] Rendering current_node={wz.current_node}")
            await self._render(call, wz.current_node, state=wz)
            await call.answer()

        @self.router.callback_query(
            StateFilter(state_filter), F.data == f"{self.prefix}_cancel"
        )
        async def handle_cancel(call: CallbackQuery, state: FSMContext):
            try:
                await self.cancel(call, state)
            except AbortWizard:
                # Middleware прервал обработку — просто подтверждаем нажатие
                await call.answer("Операция отменена.", show_alert=True)


class MenuStates(StatesGroup):
    active = State()  # один State для всего меню


class TreeMenu:
    """
    Адаптер для нелинейных меню. Mirrors TreeWizard, но использует MenuState
    вместо WizardState — нет стека посещённых узлов, произвольная навигация.

    Использование:

        menu = TreeMenu(MENU_TREE, root="main", callback_prefix="menu")
        dp.include_router(menu.router)

        @dp.message(Command("menu"))
        async def cmd_menu(message: Message, state: FSMContext):
            await menu.start(message, state)
    """

    def __init__(
        self,
        tree: dict[str, Node],
        root: str,
        callback_prefix: str = "menu",
        max_row_length: int = 30,
        on_finish=None,  # async def on_finish(call, state, data) -> None
        on_start=None,  # async def on_start(message: Message, state: FSMContext) -> None
        middleware: list[MenuMiddlewareHook] | None = None,
        external_callback_prefix: str | None = None,
        back_button_text: str = "⬅️ Назад",
    ):
        validate_tree(tree, root)  # TreeMenu требует все узлы внутри дерева
        check_callback_data_limits(tree, callback_prefix)
        self.tree = tree
        self.root = root
        self.prefix = callback_prefix
        self.max_row_length = max_row_length
        self.on_finish = on_finish
        self.on_start = on_start
        self.middleware = middleware or []
        # Внешний роутер для обработчиков, не перехватываемых TreeMenu.
        # Если external_callback_prefix задан, все кнопки с кастомным callback_data,
        # начинающимся с этого префикса, обрабатываются внешним роутером.
        self.external_router = Router()
        self.external_callback_prefix = external_callback_prefix
        if external_callback_prefix is not None:
            check_callback_data_limits(tree, external_callback_prefix)
        self.back_button_text = back_button_text
        self.router = Router()
        self._register_handlers()

    def _build_menu_keyboard(
        self, node_id: str, node: Node, state: MenuState | None = None
    ) -> InlineKeyboardMarkup:
        """
        Строит клавиатуру для меню — только опции с is_menu_item=True.
        Если передан state — разворачивает DynamicOption в обычные Option.
        """
        print(
            f"[BUILD_MENU_KEYBOARD] node_id={node_id} state_type={type(state).__name__ if state else 'None'}"
        )

        resolved_options = resolve_dynamic_options(node, state=state)
        print(
            f"[BUILD_MENU_KEYBOARD] Resolved {len(resolved_options)} options for node={node_id}"
        )

        # Фильтруем только опции для меню (MenuOption с is_menu_item=True или обычные Option)
        menu_buttons: list[InlineKeyboardButton] = []
        for i, opt in enumerate(resolved_options):
            if isinstance(opt, MenuOption) and not opt.is_menu_item:
                print(
                    f"[BUILD_MENU_KEYBOARD] Skipping option {i}: label={opt.label!r} (is_menu_item=False)"
                )
                continue
            # Определяем callback_data: кастомный или стандартный формат {prefix}:{node_id}:{index}
            if isinstance(opt, MenuOption) and opt.callback_data is not None:
                cb_data = opt.callback_data
            else:
                cb_data = f"{self.prefix}:{node_id}:{i}"

            print(
                f"[BUILD_MENU_KEYBOARD] Option {i}: label={opt.label!r} value={opt.value!r} callback_data={cb_data!r}"
            )

            btn_kwargs: dict[str, str | None] = {
                "text": opt.label,
                "callback_data": cb_data,
            }
            if isinstance(opt, URLOption) and opt.url is not None:
                btn_kwargs["url"] = opt.url
            elif isinstance(opt, SwitchOption) and opt.switch_inline_query is not None:
                btn_kwargs["switch_inline_query"] = opt.switch_inline_query
            menu_buttons.append(InlineKeyboardButton(**btn_kwargs))  # type: ignore[arg-type]

        rows = pack_buttons(menu_buttons, self.max_row_length)
        print(f"[BUILD_MENU_KEYBOARD] Built {len(rows)} button rows")

        # Кнопка "Назад" для не-корневых узлов
        if node_id != self.root:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=self.back_button_text, callback_data=f"{self.prefix}_back"
                    )
                ]
            )
            print(
                f"[BUILD_MENU_KEYBOARD] Added back button (node_id={node_id} != root={self.root})"
            )

        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def _render(self, target, node_id: str, state: MenuState | None = None):
        """Рендерит узел на экран."""
        print(f"[RENDER_MENU] node_id={node_id} target_type={type(target).__name__}")
        node = self.tree[node_id]
        kb = self._build_menu_keyboard(node_id, node, state=state)
        if isinstance(target, CallbackQuery):
            # Проверяем, изменился ли контент — если нет, пропускаем edit_text
            # (Telegram запрещает отправку идентичного контента: "message is not modified")
            current_text = target.message.text
            current_kb = target.message.reply_markup
            if current_text == node.text and current_kb == kb:
                print(
                    f"[RENDER_MENU] Content unchanged for node={node_id}, skipping edit_text"
                )
                await (
                    target.answer()
                )  # Просто подтверждаем callback без изменения контента
            else:
                await target.message.edit_text(node.text, reply_markup=kb)
                print(f"[RENDER_MENU] Edited text for node={node_id}")
        else:
            await target.answer(node.text, reply_markup=kb)
            print(f"[RENDER_MENU] Answered with text for node={node_id}")

    async def start(self, message: Message, state: FSMContext):
        """Запускает меню с корневого узла."""
        print(
            f"[TREE_MENU_START] root={self.root} user_id={getattr(message.from_user, 'id', None)} external_prefix={self.external_callback_prefix}"
        )
        # Middleware hook: menu_start
        for mw in self.middleware:
            user_id = getattr(message, "from_user", None)
            await mw(
                MenuMiddlewareData(
                    event_type="menu_start",
                    node_id=self.root,
                    user_id=user_id.id if user_id else None,
                )
            )

        ms = MenuState(current_node=self.root, parent_node=None)
        print("[TREE_MENU_START] Setting state to MenuStates.active")
        await state.set_state(MenuStates.active)
        await state.update_data(**ms.to_dict())

        # on_start hook — вызывается до отправки первого сообщения
        if self.on_start:
            print("[TREE_MENU_START] Calling on_start hook")
            await self.on_start(message, state)

        print(f"[TREE_MENU_START] Rendering root node={self.root}")
        await self._render(message, self.root, state=ms)

    async def cancel(self, target, state: FSMContext):
        """Прерывает работу с меню и очищает состояние."""
        user_id = None
        if isinstance(target, CallbackQuery):
            user_id = target.from_user.id
        else:
            user_id = getattr(target, "from_user", None)
            if user_id is not None:
                user_id = user_id.id

        for mw in self.middleware:
            await mw(MenuMiddlewareData(event_type="menu_start", user_id=user_id))

        await state.clear()

        text = "Меню закрыто."
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text)
        else:
            await target.answer(text)

    async def jump_to(self, target, target_node: str, state: FSMContext):
        """
        Перемещает пользователя на целевой узел меню без сброса данных.
        Полезно для навигации между разделами меню.
        """
        if target_node not in self.tree:
            raise TreeError(f"Целевой узел {target_node!r} отсутствует в дереве")

        data = await state.get_data()
        ms = MenuState.from_dict(data)

        new_ms = MenuState(current_node=target_node, data=ms.data)
        await state.update_data(**new_ms.to_dict())

        node = self.tree[target_node]
        kb = self._build_menu_keyboard(target_node, node, state=new_ms)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(node.text, reply_markup=kb)
        else:
            await target.answer(node.text, reply_markup=kb)

    async def switch_to_wizard(
        self,
        state: FSMContext,
        target,
        target_node: str | None = None,
        shared_data: dict | None = None,
    ):
        """
        Переводит пользователя из меню в опрос (P2).

        Если target_node не указан — переходит на корневой узел опроса.
        shared_data передаётся в middleware и сохраняется для дальнейшего использования.

        target — CallbackQuery или Message для рендеринга.
        """
        print(
            f"[SWITCH_TO_WIZARD] user_id={getattr(target, 'from_user', None)} target_node={target_node} self.prefix={self.prefix}"
        )

        # Middleware hook: transition_to_wizard
        user_id = None
        if isinstance(target, CallbackQuery):
            user_id = target.from_user.id
        else:
            user_id = getattr(target, "from_user", None)
            if user_id is not None:
                user_id = user_id.id

        for mw in self.middleware:
            await mw(
                MenuMiddlewareData(
                    event_type="transition_to_wizard",
                    user_id=user_id,
                    target_node=target_node,
                    shared_data=shared_data or {},
                )
            )

        # Сохраняем shared_data в FSMContext
        if shared_data:
            current_data = await state.get_data()
            current_data["shared_data"] = shared_data
            await state.update_data(**current_data)

        # Переключаемся на self.state_group.active
        print(
            f"[SWITCH_TO_WIZARD] Switching to {self.state_group.__name__}.active, target_node={target_node}"
        )
        await state.set_state(self.state_group.active)

        # Если target_node не указан, используем корневой узел опроса (предполагаем "start")
        if target_node is None:
            target_node = "start"

        wz = WizardState(stack=(target_node,), answers=())
        await state.update_data(**wz.to_dict())

        # ВАЖНО: self.tree — это дерево меню, а не опроса! Если target_node отсутствует в дереве меню,
        # будет KeyError. Это типичная ошибка при использовании switch_to_wizard из TreeMenu для перехода
        # в TreeWizard с другим деревом (quiz_start, survey_intro и т.д.).
        print(f"[SWITCH_TO_WIZARD] self.tree keys: {list(self.tree.keys())}")
        if target_node not in self.tree:
            raise KeyError(
                f"target_node={target_node!r} отсутствует в дереве меню (self.tree). "
                f"TreeMenu.switch_to_wizard() пытается найти узел опроса/квиза в дереве меню. "
                f"Это НЕ должно происходить — switch_to_wizard должен вызываться из TreeWizard, а не из TreeMenu."
            )

        node = self.tree[target_node]
        kb = self._build_keyboard(target_node, node, state=wz)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(node.text, reply_markup=kb)
        else:
            await target.answer(node.text, reply_markup=kb)

        print(f"[SWITCH_TO_WIZARD] Successfully switched to wizard node={target_node}")

    def _register_handlers(self):
        # Внешние callback'и обрабатываются только кастомными обработчиками,
        # зарегистрированными пользователем на external_router.
        # Автогенерированный fallback-обработчик удалён — он блокировал
        # выполнение пользовательских handler'ов (survey_btn, quiz_btn и т.д.),
        # так как перехватывал все ext:* callbacks и вызывал call.answer().

        @self.router.callback_query(
            StateFilter(MenuStates.active), F.data.startswith(f"{self.prefix}:")
        )
        async def handle_menu_choice(call: CallbackQuery, state: FSMContext):
            print(
                f"[HANDLE_MENU_CHOICE] call.data={call.data} user_id={call.from_user.id}"
            )
            _, node_id, idx_str = call.data.split(":")
            data = await state.get_data()
            ms = MenuState.from_dict(data)
            print(
                f"[HANDLE_MENU_CHOICE] Parsed: node_id={node_id}, idx_str={idx_str}, current_node={ms.current_node}"
            )

            node = self.tree[node_id]
            resolved_options = resolve_dynamic_options(node, state=ms)
            print(
                f"[HANDLE_MENU_CHOICE] Resolved {len(resolved_options)} options for node={node_id}"
            )

            if not (0 <= int(idx_str) < len(resolved_options)):
                print(
                    f"[HANDLE_MENU_CHOICE] Invalid index: {idx_str} for node={node_id}, options count={len(resolved_options)}"
                )
                await call.answer("Некорректный выбор.", show_alert=True)
                return

            opt = resolved_options[int(idx_str)]
            print(
                f"[HANDLE_MENU_CHOICE] Selected option: label={opt.label!r} value={opt.value!r} next_node={opt.next_node}"
            )

            # Middleware hook: menu_choice
            for mw in self.middleware:
                await mw(
                    MenuMiddlewareData(
                        event_type="menu_choice",
                        node_id=node_id,
                        option_index=int(idx_str),
                        user_id=call.from_user.id,
                    )
                )

            if opt.next_node is None:
                # next_node=None означает "кастомный обработчик" — не отвечаем на callback сами,
                # чтобы кастомный handler (survey_btn, quiz_btn и т.д.) мог выполнить свою работу.
                # Кастомный обработчик сам вызовет call.answer().
                print(
                    f"[HANDLE_MENU_CHOICE] next_node=None, deferring to custom handler for option={opt.value!r}"
                )
                return
            else:
                # Запоминаем текущий узел как родительский для навигации "Назад"
                new_ms = MenuState(
                    current_node=opt.next_node,
                    parent_node=node_id,
                    data=ms.data,
                )
                print(
                    f"[HANDLE_MENU_CHOICE] Navigating to next_node={opt.next_node}, parent={node_id}"
                )
                await state.update_data(**new_ms.to_dict())
                await self._render(call, opt.next_node, state=new_ms)
            await call.answer()

        @self.router.callback_query(
            StateFilter(MenuStates.active), F.data == f"{self.prefix}_back"
        )
        async def handle_menu_back(call: CallbackQuery, state: FSMContext):
            data = await state.get_data()
            ms = MenuState.from_dict(data)

            # Middleware hook: menu_back
            for mw in self.middleware:
                await mw(
                    MenuMiddlewareData(
                        event_type="menu_back",
                        node_id=ms.current_node,
                        user_id=call.from_user.id,
                    )
                )

            # Переход к родительскому узлу (или к корню если родителя нет)
            parent = ms.parent_node or self.root
            new_ms = MenuState(current_node=parent, data=ms.data)
            await state.update_data(**new_ms.to_dict())
            await self._render(call, parent, state=new_ms)
            await call.answer()

        @self.router.callback_query(
            StateFilter(MenuStates.active), F.data == f"{self.prefix}_cancel"
        )
        async def handle_menu_cancel(call: CallbackQuery, state: FSMContext):
            try:
                await self.cancel(call, state)
            except MenuAbortWizard:
                await call.answer("Операция отменена.", show_alert=True)
