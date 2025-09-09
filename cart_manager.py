# Простая in-memory корзина на пользователя
# !!! При рестарте процесса данные обнуляются (как и раньше).

_carts = {}
_last_orders = {}  # user_id -> list of items (последняя заказанная корзина)

def add_to_cart(user_id: int, item: dict):
    _carts.setdefault(user_id, [])
    _carts[user_id].append(item)

def get_cart(user_id: int):
    return _carts.get(user_id, []).copy()

def remove_from_cart(user_id: int, index: int):
    if user_id in _carts and 0 <= index < len(_carts[user_id]):
        _carts[user_id].pop(index)

def clear_cart(user_id: int):
    _carts[user_id] = []

def replace_cart(user_id: int, items: list):
    _carts[user_id] = items.copy()

# --- Последний заказ ---

def set_last_order(user_id: int, items: list):
    # сохраняем копию, чтобы не зависеть от дальнейших мутаций
    _last_orders[user_id] = [dict(x) for x in items]

def get_last_order(user_id: int):
    return [dict(x) for x in _last_orders.get(user_id, [])]
