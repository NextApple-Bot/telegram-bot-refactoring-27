from aiogram.fsm.state import State, StatesGroup


class AssortmentConfirmState(StatesGroup):
    """Подтверждение массовой загрузки ассортимента."""
    waiting_for_confirm = State()


class ArrivalConfirmState(StatesGroup):
    """Подтверждение добавления товаров через топик Приход."""
    waiting_for_confirm = State()
