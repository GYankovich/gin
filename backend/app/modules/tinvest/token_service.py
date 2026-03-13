from typing import Optional, List
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException, status

from app.modules.tinvest.methods import create_tbank_client
from app.modules.tinvest.models import ApiToken
from app.modules.tinvest.schemas import TokenCreate, TokenUpdate

logger = logging.getLogger(__name__)


class TokenService:
    """Сервис для управления API токенами"""

    @staticmethod
    async def get_user_token(db: Session, user_id: int) -> Optional[str]:
        """
        Получение активного токена пользователя (для обратной совместимости)
        """
        query = text("""
                     SELECT token, id FROM ganaly.api_tokens
                     WHERE user_id = :user_id
                       AND token_type = 'tinvest'
                       AND is_active = 1
                     ORDER BY created_at DESC
                         LIMIT 1
                     """)

        result = db.execute(query, {"user_id": user_id}).first()

        if result:
            token = result[0]
            token_id = result[1]

            # Обновляем время последнего использования
            await TokenService.update_last_used(db, token_id)

            return token

        return None

    @staticmethod
    async def get_user_tokens(
            db: Session,
            user_id: int,
            include_inactive: bool = False
    ) -> List[ApiToken]:
        """
        Получение всех токенов пользователя
        """
        query = db.query(ApiToken).filter(
            ApiToken.user_id == user_id,
            ApiToken.token_type == 'tinvest'
        )

        if not include_inactive:
            query = query.filter(ApiToken.is_active == 1)

        return query.order_by(ApiToken.created_at.desc()).all()

    @staticmethod
    async def get_token_by_id(db: Session, token_id: int, user_id: int) -> ApiToken:
        """
        Получение токена по ID (с проверкой принадлежности пользователю)
        """
        token = db.query(ApiToken).filter(
            ApiToken.id == token_id,
            ApiToken.user_id == user_id
        ).first()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Токен не найден"
            )

        return token

    @staticmethod
    async def create_token(
            db: Session,
            user_id: int,
            token_data: TokenCreate
    ) -> ApiToken:
        """
        Создание нового токена
        """
        # Проверяем валидность токена
        is_valid, message, accounts = await TokenService.test_token(token_data.token)

        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Невалидный токен: {message}"
            )

        # Создаем токен
        db_token = ApiToken(
            user_id=user_id,
            token_type=token_data.token_type,
            token=token_data.token,
            token_name=token_data.token_name,
            is_active=1,
            created_at=datetime.now(timezone.utc)
        )

        db.add(db_token)
        db.commit()
        db.refresh(db_token)

        logger.info(f"✅ Created new token for user {user_id}, id: {db_token.id}")

        return db_token

    @staticmethod
    async def update_token(
            db: Session,
            token_id: int,
            user_id: int,
            token_data: TokenUpdate
    ) -> ApiToken:
        """
        Обновление токена
        """
        token = await TokenService.get_token_by_id(db, token_id, user_id)

        # Обновляем поля
        if token_data.token_name is not None:
            token.token_name = token_data.token_name

        if token_data.is_active is not None:
            token.is_active = 1 if token_data.is_active else 0

        token.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(token)

        logger.info(f"✅ Updated token {token_id} for user {user_id}")

        return token

    @staticmethod
    async def delete_token(db: Session, token_id: int, user_id: int):
        """
        Удаление токена
        """
        token = await TokenService.get_token_by_id(db, token_id, user_id)

        db.delete(token)
        db.commit()

        logger.info(f"✅ Deleted token {token_id} for user {user_id}")

    @staticmethod
    async def test_token(token: str) -> tuple[bool, str, Optional[List]]:
        """
        Тестирование валидности токена через запрос к API
        """
        try:
            client = create_tbank_client(token)
            accounts = await client.get_accounts()

            if accounts:
                account_types = [acc.get("type", "").replace("ACCOUNT_TYPE_", "") for acc in accounts]
                account_summary = ", ".join(account_types[:3])
                if len(accounts) > 3:
                    account_summary += f" и ещё {len(accounts) - 3}"

                return True, f"Токен валиден. Найдено счетов: {len(accounts)}", accounts
            else:
                return False, "Токен валиден, но счетов не найдено", None

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                return False, "Неверный токен или токен истек", None
            elif "403" in error_msg:
                return False, "Недостаточно прав для доступа к API", None
            elif "429" in error_msg:
                return False, "Слишком много запросов, попробуйте позже", None
            else:
                return False, f"Ошибка проверки токена: {error_msg}", None

    @staticmethod
    async def update_last_used(db: Session, token_id: int):
        """
        Обновление времени последнего использования токена
        """
        try:
            token = db.query(ApiToken).filter(ApiToken.id == token_id).first()
            if token:
                token.last_used_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as e:
            logger.error(f"Error updating last_used for token {token_id}: {e}")
            db.rollback()


# Создаем экземпляр сервиса
token_service = TokenService()