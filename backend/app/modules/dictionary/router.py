#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesDictionaryRouter [1]
#/// Исходный модуль `backend/app/modules/dictionary/router.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/dictionary/router.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import logging

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from . import schemas, queries

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dictionary", tags=["Dictionary"])

@router.post("/data", response_model=List[schemas.DictionaryResponse])
async def get_dictionary(
        dictionary_data: schemas.DictionaryData,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение данных для справочника
    """
    if not dictionary_data.tableName or not dictionary_data.columnName:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не указаны tableName или columnName"
        )

    try:
        results = queries.get_dictionary_data(
            db=db,
            table_name=dictionary_data.tableName,
            column_name=dictionary_data.columnName
        )

        # Преобразование результатов в список ответов
        keys = []
        for row in results:
            keys.append(schemas.DictionaryResponse(
                id=row['id'],
                tableName=row['table_name'],
                columnName=row['column_name'],
                name=row['name'],
                description=row['description'],
                numericValue=row['num_value'],
                stringValue=row['string_value']
            ))

        return keys
    except Exception as e:
        logger.error(f"Error getting dictionary data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving dictionary data"
        )