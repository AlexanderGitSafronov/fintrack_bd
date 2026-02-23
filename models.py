from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    email         = Column(String, unique=True, index=True, nullable=False)
    username      = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow)

    categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")
    expenses   = relationship("Expense",  back_populates="user", cascade="all, delete-orphan")
    settings   = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    name       = Column(String, nullable=False)
    icon       = Column(String, default="📦")
    color      = Column(String, default="#6366f1")
    budget     = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user     = relationship("User",     back_populates="categories")
    expenses = relationship("Expense",  back_populates="category")


class Expense(Base):
    __tablename__ = "expenses"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    amount      = Column(Float, nullable=False)
    currency    = Column(String, default="UAH")
    description = Column(String, nullable=False)
    date        = Column(String, nullable=False)   # YYYY-MM-DD
    created_at  = Column(DateTime, default=datetime.utcnow)

    user     = relationship("User",     back_populates="expenses")
    category = relationship("Category", back_populates="expenses")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id       = Column(Integer, primary_key=True, index=True)
    user_id  = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    currency = Column(String, default="UAH")
    lang     = Column(String, default="uk")
    theme    = Column(String, default="light")

    user = relationship("User", back_populates="settings")
