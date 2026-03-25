# app/modules/dictionary/schemas.py

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime

class DictionaryData(BaseModel):
    tableName: str = None
    columnName: str = None

class DictionaryResponse(BaseModel):
    id: int
    tableName: str
    columnName: str
    name: str
    description: str
    numericValue: Optional[int] = None
    stringValue: Optional[str] = None
