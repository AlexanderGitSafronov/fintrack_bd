from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, ConfigDict


# ─────────────────────────── AUTH ───────────────────────────

class UserRegister(BaseModel):
    email:    EmailStr
    username: str
    password: str


class UserLogin(BaseModel):
    email:    str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:         int
    email:      str
    username:   str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user:         UserOut


# ─────────────────────────── CATEGORIES ───────────────────────────

class CategoryBase(BaseModel):
    name:   str
    icon:   str           = "📦"
    color:  str           = "#6366f1"
    budget: Optional[float] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(CategoryBase):
    pass


class CategoryOut(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id:         int
    user_id:    int
    created_at: datetime


# ─────────────────────────── EXPENSES ───────────────────────────

class ExpenseBase(BaseModel):
    amount:      float
    currency:    str           = "RUB"
    description: str
    date:        str           # YYYY-MM-DD
    category_id: Optional[int] = None


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseUpdate(ExpenseBase):
    pass


class ExpenseOut(ExpenseBase):
    model_config = ConfigDict(from_attributes=True)

    id:         int
    user_id:    int
    created_at: datetime
    category:   Optional[CategoryOut] = None


# ─────────────────────────── SETTINGS ───────────────────────────

class SettingsUpdate(BaseModel):
    currency: Optional[str] = None
    lang:     Optional[str] = None
    theme:    Optional[str] = None


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: str
    lang:     str
    theme:    str


# ─────────────────────────── EXPORT / IMPORT ───────────────────────────

class ExportData(BaseModel):
    categories: List[CategoryOut]
    expenses:   List[ExpenseOut]
    settings:   SettingsOut


class ImportData(BaseModel):
    categories: List[CategoryCreate]
    expenses:   List[ExpenseCreate]
