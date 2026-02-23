from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List

from database import engine, Base, get_db
import models, schemas, auth
from routers import auth as auth_router
from routers import categories as categories_router
from routers import expenses as expenses_router
from routers import settings as settings_router
from routers import chat as chat_router

# Create all DB tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="FinTrack API",
    description="Backend API for FinTrack — personal expense tracker",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow all origins (API is protected by JWT tokens)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router.router)
app.include_router(categories_router.router)
app.include_router(expenses_router.router)
app.include_router(settings_router.router)
app.include_router(chat_router.router)


# ─────────────────────────── ROOT / HEALTH ───────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {"message": "FinTrack API is running ✅", "docs": "/docs"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


# ─────────────────────────── EXPORT / IMPORT ───────────────────────────

@app.get("/api/export", response_model=schemas.ExportData, tags=["Data"])
def export_data(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Export all user data (categories + expenses + settings) as JSON."""
    categories = (
        db.query(models.Category)
        .filter(models.Category.user_id == current_user.id)
        .all()
    )
    expenses = (
        db.query(models.Expense)
        .filter(models.Expense.user_id == current_user.id)
        .order_by(models.Expense.date.desc())
        .all()
    )
    settings = (
        db.query(models.UserSettings)
        .filter(models.UserSettings.user_id == current_user.id)
        .first()
    ) or models.UserSettings(user_id=current_user.id)

    return schemas.ExportData(
        categories=[schemas.CategoryOut.model_validate(c) for c in categories],
        expenses=[schemas.ExpenseOut.model_validate(e) for e in expenses],
        settings=schemas.SettingsOut.model_validate(settings),
    )


@app.post("/api/import", tags=["Data"])
def import_data(
    data: schemas.ImportData,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Import categories and expenses. Existing data is NOT deleted.
    Categories are matched by name — existing ones are reused, new ones are created.
    """
    # Build map of existing categories by name
    existing = {
        c.name: c
        for c in db.query(models.Category)
        .filter(models.Category.user_id == current_user.id)
        .all()
    }

    # Import categories
    cat_id_map: dict[str, int] = {}   # old name → new DB id
    new_cats = 0
    for cat_data in data.categories:
        if cat_data.name in existing:
            cat_id_map[cat_data.name] = existing[cat_data.name].id
        else:
            cat = models.Category(**cat_data.model_dump(), user_id=current_user.id)
            db.add(cat)
            db.flush()
            cat_id_map[cat_data.name] = cat.id
            new_cats += 1

    # Import expenses
    new_exps = 0
    for exp_data in data.expenses:
        exp = models.Expense(
            user_id=current_user.id,
            amount=exp_data.amount,
            currency=exp_data.currency,
            description=exp_data.description,
            date=exp_data.date,
            category_id=exp_data.category_id,
        )
        db.add(exp)
        new_exps += 1

    db.commit()
    return {
        "imported_categories": new_cats,
        "imported_expenses": new_exps,
    }
