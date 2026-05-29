from aiogram.fsm.state import State, StatesGroup


class AssortmentConfirmState(StatesGroup):
    waiting_for_confirm = State()

class ArrivalConfirmState(StatesGroup):
    waiting_for_confirm = State()
