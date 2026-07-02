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

from .core import Node, WizardState, choose, go_back, validate_tree, StaleChoiceError, TreeError


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


def pack_buttons(
    buttons: list[InlineKeyboardButton],
    max_row_length: int = 30,
) -> list[list[InlineKeyboardButton]]:
    """Авто-раскладка кнопок по рядам с учётом длины текста."""
    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    current_length = 0

    for button in buttons:
        button_length = len(button.text) + 5
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
    ):
        validate_tree(tree, root)  # падаем при старте бота, а не в рантайме
        check_callback_data_limits(tree, callback_prefix)
        self.tree = tree
        self.root = root
        self.prefix = callback_prefix
        self.max_row_length = max_row_length
        self.on_finish = on_finish
        self.router = Router()
        self._register_handlers()

    def _build_keyboard(self, node_id: str, node: Node) -> InlineKeyboardMarkup:
        buttons = [
            InlineKeyboardButton(
                text=opt.label, callback_data=f"{self.prefix}:{node_id}:{i}"
            )
            for i, opt in enumerate(node.options)
        ]
        rows = pack_buttons(buttons, self.max_row_length)
        if node_id != self.root:
            rows.append(
                [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{self.prefix}_back")]
            )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def _render(self, target, node_id: str):
        node = self.tree[node_id]
        kb = self._build_keyboard(node_id, node)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(node.text, reply_markup=kb)
        else:
            await target.answer(node.text, reply_markup=kb)

    async def start(self, message: Message, state: FSMContext):
        wz = WizardState.start(self.root)
        await state.set_state(WizardStates.active)
        await state.update_data(**wz.to_dict())
        await self._render(message, self.root)

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

            await state.update_data(**new_wz.to_dict())

            if is_final:
                if self.on_finish:
                    await self.on_finish(call, state, new_wz.answers)
                await state.clear()
            else:
                await self._render(call, opt.next_node)
            await call.answer()

        @self.router.callback_query(
            StateFilter(WizardStates.active), F.data == f"{self.prefix}_back"
        )
        async def handle_back(call: CallbackQuery, state: FSMContext):
            data = await state.get_data()
            wz = go_back(WizardState.from_dict(data))
            await state.update_data(**wz.to_dict())
            await self._render(call, wz.current_node)
            await call.answer()
