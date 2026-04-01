#!/usr/bin/env python
"""
Ручной тест генерации сигнала и выставления заявки с логированием в robot_logs
"""
import sys
import asyncio
from pathlib import Path
from datetime import datetime, timezone
import json

backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.database import SessionLocal
from app.modules.tinvest.methods.instruments import InstrumentsClient
from app.modules.robots.trading.costs import TradingCosts
from sqlalchemy import text

TOKEN = "t.mFu8tCebjY2gV8ZfgxYtiGGeSmOWaTxnVztMOqzd2Yi5PQktfT3zPLJdkZ-QDmk6pmUHsIclK2GzuH84bqL80g"
ACCOUNT_ID = "2004129678"
FIGI = "BBG004730N88"
QUANTITY = 1
PRICE = 315.21
ROBOT_ID = 999
USER_ID = 1
TOKEN_ID = 999
def write_log_to_db(db, endpoint, request_data, response_data=None, error_message=None, started_at=None):
    """Записывает лог в robot_logs — всё в response_data"""
    finished_at = datetime.now(timezone.utc)
    started_at = started_at or finished_at
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    # Формируем response_data: при ошибке пишем просто текст
    final_response_data = response_data
    if error_message:
        final_response_data = error_message  # ← просто текст ошибки

    query = """
            INSERT INTO ganaly.robot_logs
            (robot_name, robot_version, token_id, user_id, endpoint,
             request_data, response_data, response_status,
             started_at, finished_at, duration_ms, success)
            VALUES
                (:robot_name, :robot_version, :token_id, :user_id, :endpoint,
                 :request_data, :response_data, :response_status,
                 :started_at, :finished_at, :duration_ms, :success)
                RETURNING id \
            """

    try:
        result = db.execute(
            text(query),
            {
                "robot_name": f"test_robot_{ROBOT_ID}",
                "robot_version": "1.0.0",
                "token_id": TOKEN_ID,
                "user_id": USER_ID,
                "endpoint": endpoint,
                "request_data": json.dumps(request_data, ensure_ascii=False, default=str),
                "response_data": json.dumps(final_response_data, ensure_ascii=False, default=str) if final_response_data else None,
                "response_status": 200 if not error_message else 500,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "success": 1 if not error_message else 0
            }
        ).first()

        db.commit()

        if result:
            print(f"   📝 Лог сохранен: ID={result[0]}")
        return result[0] if result else None
    except Exception as e:
        print(f"   ⚠️ Ошибка сохранения лога: {e}")
        db.rollback()
        return None

async def test_signal():
    print("=" * 60)
    print("🧪 Ручной тест сигнала и заявки с логированием в robot_logs")
    print("=" * 60)

    print(f"\n📊 Параметры теста:")
    print(f"   FIGI: {FIGI}")
    print(f"   Цена: {PRICE}")
    print(f"   Количество: {QUANTITY}")
    print(f"   Robot ID: {ROBOT_ID}")

    db = SessionLocal()

    try:
        # 1. Генерируем сигнал
        print("\n🎯 ШАГ 1: Генерация сигнала")
        signal = {
            "figi": FIGI,
            "signal": "BUY",
            "price": PRICE,
            "quantity": QUANTITY,
            "strategy": "test"
        }
        print(f"   Сигнал: BUY {QUANTITY} лотов {FIGI} по {PRICE}")

        # 2. Рассчитываем комиссию
        print("\n💰 ШАГ 2: Расчёт комиссии")
        costs = TradingCosts(PRICE, QUANTITY, is_buy=True)
        commission = costs.calculate_commission()
        break_even = costs.calculate_break_even_price()
        print(f"   Комиссия: {commission:.2f} руб.")
        print(f"   Безубыточная цена: {break_even:.2f} руб.")

        # 3. Сохраняем сигнал в БД
        print("\n💾 ШАГ 3: Сохранение сигнала в БД")
        signal_query = """
                       INSERT INTO ganaly.robot_signals
                       (robot_id, figi, signal_type, signal_strength, price_at_signal, was_executed, created_at)
                       VALUES
                           (:robot_id, :figi, :signal_type, :signal_strength, :price, 0, :now)
                           RETURNING id \
                       """

        signal_result = db.execute(
            text(signal_query),
            {
                "robot_id": ROBOT_ID,
                "figi": FIGI,
                "signal_type": "buy",
                "signal_strength": 100,
                "price": PRICE,
                "now": datetime.now(timezone.utc)
            }
        ).first()

        if signal_result:
            print(f"   ✅ Сигнал сохранен: ID={signal_result[0]}")
        else:
            print(f"   ⚠️ Сигнал не сохранен")

        db.commit()

        # 4. Выставляем заявку с логированием
        print("\n📊 ШАГ 4: Выставление заявки через REST")
        client = InstrumentsClient(TOKEN)

        request_data = {
            "figi": FIGI,
            "quantity": QUANTITY,
            "price": PRICE,
            "direction": "ORDER_DIRECTION_BUY",
            "account_id": ACCOUNT_ID
        }

        started_at = datetime.now(timezone.utc)

        try:
            order = await client.post_order(
                figi=FIGI,
                quantity=QUANTITY,
                price=PRICE,
                direction="ORDER_DIRECTION_BUY",
                account_id=ACCOUNT_ID
            )

            order_id = order.get("orderId")
            order_status = order.get("executionReportStatus")

            print(f"   ✅ Заявка отправлена!")
            print(f"   Order ID: {order_id}")
            print(f"   Статус: {order_status}")

            # Логируем успешную заявку
            write_log_to_db(
                db=db,
                endpoint="post_order",
                request_data=request_data,
                response_data=order,
                started_at=started_at
            )

            # 5. Сохраняем сделку в БД
            print("\n💾 ШАГ 5: Сохранение сделки в БД")

            trade_query = """
                          INSERT INTO ganaly.robot_trades
                          (robot_id, figi, side, quantity, price, total_amount,
                           entry_price, commission, status, order_id, created_at)
                          VALUES
                              (:robot_id, :figi, :side, :quantity, :price, :total_amount,
                               :entry_price, :commission, :status, :order_id, :now)
                              RETURNING id \
                          """

            trade_result = db.execute(
                text(trade_query),
                {
                    "robot_id": ROBOT_ID,
                    "figi": FIGI,
                    "side": "buy",
                    "quantity": QUANTITY,
                    "price": PRICE,
                    "total_amount": QUANTITY * PRICE,
                    "entry_price": PRICE,
                    "commission": commission,
                    "status": "open" if order_status in ["NEW", "PARTIALLYFILL"] else "pending",
                    "order_id": order_id,
                    "now": datetime.now(timezone.utc)
                }
            ).first()

            if trade_result:
                print(f"   ✅ Сделка сохранена: ID={trade_result[0]}")
            else:
                print(f"   ⚠️ Сделка не сохранена")

            db.commit()

        except Exception as e:
            error_msg = str(e)
            print(f"   ❌ Ошибка: {error_msg}")

            # Логируем ошибку
            log_id = write_log_to_db(
                db=db,
                endpoint="post_order",
                request_data=request_data,
                error_message=error_msg,
                started_at=started_at
            )
            print(f"   📝 Ошибка залогирована в robot_logs ID={log_id}")

            db.rollback()

        # 6. Проверяем записи в БД
        print("\n📋 ШАГ 6: Проверка записей в БД")

        # Проверяем сигналы
        check_signals = db.execute(
            text("SELECT id, figi, signal_type, price_at_signal FROM ganaly.robot_signals WHERE robot_id = :robot_id ORDER BY id DESC LIMIT 3"),
            {"robot_id": ROBOT_ID}
        ).fetchall()

        # Проверяем сделки
        check_trades = db.execute(
            text("SELECT id, figi, side, quantity, price, status, order_id FROM ganaly.robot_trades WHERE robot_id = :robot_id ORDER BY id DESC LIMIT 3"),
            {"robot_id": ROBOT_ID}
        ).fetchall()

        # Проверяем логи
        check_logs = db.execute(
            text("SELECT id, endpoint, success, error_message FROM ganaly.robot_logs WHERE robot_id = :robot_id ORDER BY id DESC LIMIT 3"),
            {"robot_id": ROBOT_ID}
        ).fetchall()

        print(f"\n   Последние сигналы:")
        for row in check_signals:
            print(f"      ID={row[0]}, {row[1]}, {row[2]}, {row[3]}")

        print(f"\n   Последние сделки:")
        for row in check_trades:
            print(f"      ID={row[0]}, {row[1]}, {row[2]}, {row[3]}, {row[4]}, {row[5]}, {row[6]}")

        print(f"\n   Последние логи:")
        for row in check_logs:
            print(f"      ID={row[0]}, {row[1]}, success={row[2]}, error={row[3]}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(test_signal())