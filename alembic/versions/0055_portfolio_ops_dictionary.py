"""Seed PORTFOLIO_OPERATIONS dictionary for OPERATION_TYPE and STATUS.

Revision ID: 0055_portfolio_ops_dictionary
Revises: 0054_moex_securities_cron
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0055_portfolio_ops_dictionary"
down_revision = "0054_moex_securities_cron"
branch_labels = None
depends_on = None

# (num_value, string_value, name, description)
_OPERATION_TYPES = [
    (1, "OPERATION_TYPE_BUY", "Покупка", "Покупка инструмента"),
    (2, "OPERATION_TYPE_SELL", "Продажа", "Продажа инструмента"),
    (3, "OPERATION_TYPE_BUY_CARD", "Покупка (карта)", "Покупка с карты"),
    (4, "OPERATION_TYPE_SELL_CARD", "Продажа (карта)", "Продажа на карту"),
    (5, "OPERATION_TYPE_BUY_MARGIN", "Покупка (маржа)", "Маржинальная покупка"),
    (6, "OPERATION_TYPE_SELL_MARGIN", "Продажа (маржа)", "Маржинальная продажа"),
    (7, "OPERATION_TYPE_INPUT", "Пополнение", "Ввод денежных средств"),
    (8, "OPERATION_TYPE_OUTPUT", "Вывод", "Вывод денежных средств"),
    (9, "OPERATION_TYPE_OUTPUT_SECURITIES", "Вывод ЦБ", "Вывод ценных бумаг"),
    (10, "OPERATION_TYPE_DIVIDEND", "Дивиденд", "Выплата дивидендов"),
    (11, "OPERATION_TYPE_DIVIDEND_TAX", "Налог на дивиденды", "Налог с дивидендов"),
    (12, "OPERATION_TYPE_COUPON", "Купон", "Купонный доход"),
    (13, "OPERATION_TYPE_BROKER_FEE", "Комиссия брокера", "Комиссия брокера"),
    (14, "OPERATION_TYPE_SERVICE_FEE", "Сервисная комиссия", "Сервисная комиссия"),
    (15, "OPERATION_TYPE_TRACK_MFEE", "Комиссия за сопровождение", "Комиссия за сопровождение"),
    (16, "OPERATION_TYPE_TRACK_PFEE", "Комиссия за результат", "Комиссия за результат"),
    (17, "OPERATION_TYPE_TAX", "Налог", "Налоговый платёж"),
    (18, "OPERATION_TYPE_TAX_CORRECTION", "Корректировка налога", "Корректировка налога"),
    (19, "OPERATION_TYPE_OVERNIGHT", "Overnight", "Перенос позиции / overnight"),
    (20, "OPERATION_TYPE_BOND_REPAYMENT_FULL", "Погашение облигации", "Полное погашение облигации"),
    (21, "OPERATION_TYPE_UNSPECIFIED", "Не указано", "Тип операции не указан"),
    (22, "ORDER_BUY", "Ордер: покупка", "Исполнение ордера на покупку"),
    (23, "ORDER_SELL", "Ордер: продажа", "Исполнение ордера на продажу"),
    (24, "BYBIT_TRADE", "Сделка ByBit", "Торговая сделка ByBit"),
    (25, "BYBIT_SETTLEMENT", "Расчёт ByBit", "Settlement ByBit"),
    (26, "BYBIT_LIQUIDATION", "Ликвидация ByBit", "Ликвидация позиции ByBit"),
    (27, "BYBIT_TRANSFER_IN", "Перевод ByBit (вход)", "Входящий перевод ByBit"),
    (28, "BYBIT_TRANSFER_OUT_UNIFIED", "Перевод ByBit (выход)", "Исходящий перевод ByBit"),
    (29, "BYBIT_FUND_IN_COPY_TRADING", "Copy trading (вход)", "Ввод средств copy trading ByBit"),
]

_STATUSES = [
    (1, "OPERATION_STATE_EXECUTED", "Исполнено", "Операция исполнена"),
    (2, "OPERATION_STATE_CANCELED", "Отменено", "Операция отменена"),
    (3, "OPERATION_STATE_PROGRESS", "В процессе", "Операция в процессе"),
    (4, "OPERATION_STATE_UNSPECIFIED", "Не указано", "Статус не указан"),
    (5, "Filled", "Исполнено", "Ордер исполнен"),
]


def _upsert_dictionary_rows(table_name: str, column_name: str, rows: list) -> None:
    for num_value, string_value, name, description in rows:
        op.execute(
            sa.text(
                """
                INSERT INTO dictionary
                    (table_name, column_name, num_value, string_value, name, description, hide_from_ui)
                SELECT
                    :table_name,
                    :column_name,
                    :num_value,
                    :string_value,
                    :name,
                    :description,
                    0
                WHERE NOT EXISTS (
                    SELECT 1 FROM dictionary
                    WHERE table_name = :table_name
                      AND column_name = :column_name
                      AND string_value = :string_value
                )
                """
            ).bindparams(
                table_name=table_name,
                column_name=column_name,
                num_value=num_value,
                string_value=string_value,
                name=name,
                description=description,
            )
        )


def upgrade() -> None:
    _upsert_dictionary_rows("PORTFOLIO_OPERATIONS", "OPERATION_TYPE", _OPERATION_TYPES)
    _upsert_dictionary_rows("PORTFOLIO_OPERATIONS", "STATUS", _STATUSES)


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM dictionary
            WHERE table_name = 'PORTFOLIO_OPERATIONS'
              AND column_name IN ('OPERATION_TYPE', 'STATUS')
            """
        )
    )
