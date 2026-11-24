"""DEPRECATED: use app.modules.portfolio.order_registry (portfolio_orders).

Left for import compatibility; new code must not write to account_orders.
"""

from app.modules.portfolio.order_registry import (  # noqa: F401
    SOURCE_EXTERNAL as ORDER_TYPE_EXTERNAL,
    SOURCE_MANUAL as ORDER_TYPE_MANUAL,
    SOURCE_ROBOT as ORDER_TYPE_ROBOT,
    insert_pending_order as insert_account_order,
    insert_robot_orders_batch,
    load_portfolio_orders as load_account_orders,
    resolve_portfolio_account_pk,
    update_order_by_pk as update_account_order_by_id,
    upsert_broker_order,
)
