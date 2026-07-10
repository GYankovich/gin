from __future__ import annotations

from app.modules.robots.portfolio_updater.robot import PortfolioUpdaterRobot


def test_normalize_bybit_portfolio_to_snapshot_shape():
    robot = PortfolioUpdaterRobot()
    raw = {
        "wallet_balance": [
            {
                "totalEquity": "1250.5",
                "accountIMRateByMp": "0",
                "coin": [
                    {"coin": "BTC", "walletBalance": "0.01"},
                    {"coin": "USDT", "walletBalance": "500"},
                    {"coin": "ETH", "walletBalance": "0"},
                ],
            }
        ]
    }
    out = robot._normalize_bybit_portfolio(raw)
    assert out["total_amount_portfolio"]["decimal"] == 1250.5
    assert out["total_amount_portfolio"]["currency"] == "USDT"
    tickers = [p["ticker"] for p in out["positions"]]
    assert tickers == ["BTC", "USDT"]
    assert all(p["class_code"] == "BYBIT" for p in out["positions"])

