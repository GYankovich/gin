# app/modules/dictionary/queries.py
from sqlalchemy.orm import Session
from typing import List, Any, Optional, Dict
from sqlalchemy import text


def get_dictionary_data(
        db: Session,
        table_name: str,
        column_name: str,
        num_value: Optional[int] = None,
        string_value: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Получение данных из справочника
    """
    # Базовый запрос
    query = text("""
                 SELECT d.id,
                        d.table_name,
                        d.column_name,
                        d."name",
                        d.description,
                        d.num_value,
                        d.string_value
                 FROM ganaly.dictionary d
                 WHERE d.table_name = :tableName
                   AND d.column_name = :columnName
                   AND d.hide_from_ui = 0
                 """)

    params = {"tableName": table_name, "columnName": column_name}

    # Добавляем фильтрацию по числовому значению, если указано
    if num_value is not None:
        query = text(f"""
            {query.text}
            AND d.num_value = :numValue
        """)
        params["numValue"] = num_value

    # Добавляем фильтрацию по строковому значению, если указано
    if string_value is not None:
        query = text(f"""
            {query.text}
            AND d.string_value = :stringValue
        """)
        params["stringValue"] = string_value

    # Выполняем запрос
    result = db.execute(query, params)

    # Всегда возвращаем список записей
    return result.mappings().all()