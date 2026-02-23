from fastapi import APIRouter, HTTPException, Depends, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db
import models, schemas, auth

router = APIRouter(prefix="/api/expenses", tags=["Expenses"])


@router.get("", response_model=List[schemas.ExpenseOut])
def list_expenses(
    category_id: Optional[int] = Query(None,  description="Filter by category ID"),
    date_from:   Optional[str] = Query(None,  description="Start date YYYY-MM-DD"),
    date_to:     Optional[str] = Query(None,  description="End date YYYY-MM-DD"),
    search:      Optional[str] = Query(None,  description="Search in description"),
    limit:       int           = Query(1000,  ge=1, le=5000),
    offset:      int           = Query(0,     ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """List expenses with optional filters."""
    q = db.query(models.Expense).filter(models.Expense.user_id == current_user.id)

    if category_id is not None:
        q = q.filter(models.Expense.category_id == category_id)
    if date_from:
        q = q.filter(models.Expense.date >= date_from)
    if date_to:
        q = q.filter(models.Expense.date <= date_to)
    if search:
        q = q.filter(models.Expense.description.ilike(f"%{search}%"))

    return q.order_by(models.Expense.date.desc(), models.Expense.id.desc()).offset(offset).limit(limit).all()


@router.post("", response_model=schemas.ExpenseOut, status_code=status.HTTP_201_CREATED)
def create_expense(
    data: schemas.ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Create a new expense."""
    if data.category_id:
        _verify_category(db, data.category_id, current_user.id)

    expense = models.Expense(**data.model_dump(), user_id=current_user.id)
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@router.put("/{exp_id}", response_model=schemas.ExpenseOut)
def update_expense(
    exp_id: int,
    data: schemas.ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Update an expense by ID."""
    expense = _get_expense(db, exp_id, current_user.id)

    if data.category_id:
        _verify_category(db, data.category_id, current_user.id)

    for field, value in data.model_dump().items():
        setattr(expense, field, value)
    db.commit()
    db.refresh(expense)
    return expense


@router.delete("/{exp_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Delete an expense by ID."""
    expense = _get_expense(db, exp_id, current_user.id)
    db.delete(expense)
    db.commit()


# ── helpers ──

def _get_expense(db: Session, exp_id: int, user_id: int) -> models.Expense:
    exp = db.query(models.Expense).filter(
        models.Expense.id == exp_id,
        models.Expense.user_id == user_id,
    ).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Expense not found")
    return exp


def _verify_category(db: Session, cat_id: int, user_id: int) -> None:
    cat = db.query(models.Category).filter(
        models.Category.id == cat_id,
        models.Category.user_id == user_id,
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
