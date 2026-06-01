from aiogram.fsm.state import State, StatesGroup


class AssortmentConfirmState(StatesGroup):
    """Состояние подтверждения загрузки ассортимента."""
    waiting_for_confirm = State()


class ArrivalConfirmState(StatesGroup):
    """Состояние подтверждения добавления товаров через топик Приход."""
    waiting_for_confirm = State()
