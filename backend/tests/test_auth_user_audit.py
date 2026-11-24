"""Регистрация, смена профиля и сброс пароля пишут актёра, дату и статус контакта."""
from datetime import datetime, timezone

from app.modules.auth.models import STATUS_ON
from app.modules.auth.schemas import PasswordResetConfirm, UserChange
from app.modules.auth.service import (
    ACTOR_CHANGE_PASS,
    ACTOR_REGISTRATION_CONFIRM,
    ACTOR_USERS_CHANGE,
    AuthService,
)


def _compact(sql: str) -> str:
    return " ".join(sql.split())


class _Db:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


def test_registration_confirm_writes_actor_and_active_email():
    service = AuthService()
    calls = []

    def execute(query, params, fetch_one=False):
        calls.append((_compact(query), params))
        if 'INSERT INTO "user"' in query:
            return (3,)
        return None

    service._execute = execute
    service.db = _Db()
    service._persist_user(
        login="ada",
        password_hash="hash",
        email="ada@example.com",
        now=datetime.now(timezone.utc),
    )

    user_sql, user_params = next(item for item in calls if 'INSERT INTO "user"' in item[0])
    email_sql, email_params = next(item for item in calls if "INSERT INTO user_email" in item[0])
    assert "usercre" in user_sql
    assert user_params["usercre"] == ACTOR_REGISTRATION_CONFIRM
    assert "status" in email_sql
    assert email_params["status"] == STATUS_ON


def test_change_user_stamps_user_and_versions_the_email():
    service = AuthService()
    calls = []
    profiles = {"n": 0}

    def execute(query, params, fetch_one=False):
        sql = _compact(query)
        calls.append((sql, params))
        if 'FROM "user" u' in sql:
            profiles["n"] += 1
            email = "old@example.com" if profiles["n"] == 1 else "new@example.com"
            return (5, "ada", datetime.now(timezone.utc), 1, email, "+79990001122")
        return None

    service._execute = execute
    db = _Db()
    updated = service.change_user(
        db,
        5,
        UserChange(login="ada", email="new@example.com", phone="+79990001122"),
    )

    assert updated["email"] == "new@example.com"
    assert db.commits == 1
    user_update = next(params for sql, params in calls if sql.startswith('UPDATE "user"'))
    assert user_update["usermod"] == ACTOR_USERS_CHANGE
    assert isinstance(user_update["date_modification"], datetime)
    assert abs((datetime.now(timezone.utc) - user_update["date_modification"]).total_seconds()) < 5
    assert any(sql.startswith("UPDATE user_email") and "status = 0" in sql for sql, _ in calls)
    email_insert = next(params for sql, params in calls if sql.startswith("INSERT INTO user_email"))
    assert email_insert["email"] == "new@example.com"
    assert email_insert["status"] == STATUS_ON
    assert email_insert["usercre"] == "ada"
    assert not any(sql.startswith("INSERT INTO user_phone") or sql.startswith("UPDATE user_phone") for sql, _ in calls)
    assert not any(sql.startswith("DELETE FROM user_email") for sql, _ in calls)


def test_change_user_keeps_the_same_contact_row():
    service = AuthService()
    calls = []

    def execute(query, params, fetch_one=False):
        sql = _compact(query)
        calls.append(sql)
        if 'FROM "user" u' in sql:
            return (5, "ada", datetime.now(timezone.utc), 1, "ada@example.com", None)
        return None

    service._execute = execute
    service.change_user(db=_Db(), user_id=5, data=UserChange(login="ada2", email="ada@example.com"))
    assert any(sql.startswith('UPDATE "user"') for sql in calls)
    assert not any("user_email" in sql and sql.startswith(("UPDATE", "INSERT")) for sql in calls)


def test_change_user_retires_a_cleared_phone():
    service = AuthService()
    calls = []

    def execute(query, params, fetch_one=False):
        sql = _compact(query)
        calls.append((sql, params))
        if 'FROM "user" u' in sql:
            return (5, "ada", datetime.now(timezone.utc), 1, "ada@example.com", "+79990001122")
        return None

    service._execute = execute
    service.change_user(db=_Db(), user_id=5, data=UserChange(login="ada", email="ada@example.com", phone=None))
    phone_close = next(params for sql, params in calls if sql.startswith("UPDATE user_phone"))
    assert phone_close["usermod"] == ACTOR_USERS_CHANGE
    assert not any(sql.startswith("INSERT INTO user_phone") for sql, _ in calls)


def test_reset_password_stamps_actor_and_date():
    service = AuthService()
    calls = []
    service._user_from_reset_token = lambda token: {"id": 5, "login": "ada", "email": "ada@example.com"}

    def execute(query, params, fetch_one=False):
        calls.append((_compact(query), params))
        return None

    service._execute = execute
    db = _Db()
    service.reset_password(
        db,
        PasswordResetConfirm(token="a" * 24, password="newpassword"),
    )

    assert db.commits == 1
    _sql, params = next(item for item in calls if item[0].startswith('UPDATE "user"'))
    assert params["usermod"] == ACTOR_CHANGE_PASS
    assert isinstance(params["date_modification"], datetime)
    assert abs((datetime.now(timezone.utc) - params["date_modification"]).total_seconds()) < 5
    assert params["password_hash"] != "newpassword"
    assert any(item[0].startswith("DELETE FROM email_confirmation") for item in calls)
