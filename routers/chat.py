import os
import json
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List
from openai import OpenAI

from database import get_db
import models, auth

router = APIRouter(prefix="/api/chat", tags=["Chat"])


# ─────────────────────────── SCHEMAS ───────────────────────────

class ChatMessage(BaseModel):
    role: str      # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    lang: str = "en"


# ─────────────────────────── TOOLS DEFINITION ───────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_expense",
            "description": "Add a new expense for the user",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount":        {"type": "number", "description": "Amount of the expense (positive number)"},
                    "description":   {"type": "string", "description": "What was the expense for"},
                    "category_name": {"type": "string", "description": "Category name (use list_categories to get available ones)"},
                    "date":          {"type": "string", "description": "Date in YYYY-MM-DD format, defaults to today if not specified"},
                },
                "required": ["amount", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending_summary",
            "description": "Get total spending and transaction count for a given period",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["today", "yesterday", "week", "month", "year"],
                        "description": "Time period",
                    }
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_expenses",
            "description": "List recent expenses, optionally filtered by category",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit":         {"type": "integer", "description": "Max number of expenses (default 10, max 20)"},
                    "category_name": {"type": "string",  "description": "Filter by category name (optional)"},
                    "period":        {"type": "string",  "enum": ["today", "week", "month"], "description": "Filter by period (optional)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": "Get all expense categories with monthly spending and budget info",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_categories",
            "description": "Get top spending categories for a period",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "enum": ["week", "month", "year"], "description": "Time period"},
                    "limit":  {"type": "integer", "description": "Number of top categories (default 3)"},
                },
                "required": ["period"],
            },
        },
    },
]


# ─────────────────────────── TOOL EXECUTION ───────────────────────────

def _date_range(period: str):
    today = date.today()
    if period == "today":
        return str(today), str(today)
    if period == "yesterday":
        d = today - timedelta(days=1)
        return str(d), str(d)
    if period == "week":
        return str(today - timedelta(days=7)), str(today)
    if period == "month":
        return str(today.replace(day=1)), str(today)
    if period == "year":
        return str(today.replace(month=1, day=1)), str(today)
    return str(today), str(today)


def execute_tool(name: str, args: dict, user_id: int, db: Session) -> str:

    if name == "list_categories":
        cats = db.query(models.Category).filter(models.Category.user_id == user_id).all()
        today = date.today()
        month_start = str(today.replace(day=1))
        result = []
        for c in cats:
            spent = db.query(func.sum(models.Expense.amount)).filter(
                models.Expense.user_id == user_id,
                models.Expense.category_id == c.id,
                models.Expense.date >= month_start,
            ).scalar() or 0
            result.append({
                "name": c.name,
                "icon": c.icon,
                "budget": c.budget,
                "spent_this_month": round(spent, 2),
            })
        return json.dumps(result, ensure_ascii=False)

    if name == "get_spending_summary":
        period = args.get("period", "month")
        date_from, date_to = _date_range(period)
        total = db.query(func.sum(models.Expense.amount)).filter(
            models.Expense.user_id == user_id,
            models.Expense.date >= date_from,
            models.Expense.date <= date_to,
        ).scalar() or 0
        count = db.query(func.count(models.Expense.id)).filter(
            models.Expense.user_id == user_id,
            models.Expense.date >= date_from,
            models.Expense.date <= date_to,
        ).scalar() or 0
        return json.dumps({"period": period, "total": round(total, 2), "transactions": count}, ensure_ascii=False)

    if name == "list_expenses":
        limit        = min(int(args.get("limit", 10)), 20)
        category_name = args.get("category_name")
        period       = args.get("period")

        q = db.query(models.Expense).filter(models.Expense.user_id == user_id)
        if period:
            date_from, date_to = _date_range(period)
            q = q.filter(models.Expense.date >= date_from, models.Expense.date <= date_to)
        if category_name:
            cat = db.query(models.Category).filter(
                models.Category.user_id == user_id,
                models.Category.name.ilike(f"%{category_name}%"),
            ).first()
            if cat:
                q = q.filter(models.Expense.category_id == cat.id)
        exps = q.order_by(models.Expense.date.desc()).limit(limit).all()

        result = []
        for e in exps:
            cat_name = e.category.name if e.category else None
            result.append({
                "id": e.id, "date": e.date, "amount": e.amount,
                "description": e.description, "category": cat_name,
            })
        return json.dumps(result, ensure_ascii=False)

    if name == "add_expense":
        amount      = float(args["amount"])
        description = args["description"]
        exp_date    = args.get("date", str(date.today()))
        category_name = args.get("category_name")

        category_id = None
        if category_name:
            cat = db.query(models.Category).filter(
                models.Category.user_id == user_id,
                models.Category.name.ilike(f"%{category_name}%"),
            ).first()
            if cat:
                category_id = cat.id

        settings = db.query(models.UserSettings).filter(
            models.UserSettings.user_id == user_id
        ).first()
        currency = settings.currency if settings else "USD"

        exp = models.Expense(
            user_id=user_id, amount=amount, description=description,
            date=exp_date, currency=currency, category_id=category_id,
        )
        db.add(exp)
        db.commit()
        db.refresh(exp)
        cat_name = exp.category.name if exp.category else None
        return json.dumps({
            "success": True, "id": exp.id, "amount": amount,
            "description": description, "date": exp_date, "category": cat_name,
        }, ensure_ascii=False)

    if name == "get_top_categories":
        period = args.get("period", "month")
        limit  = min(int(args.get("limit", 3)), 10)
        date_from, date_to = _date_range(period)

        rows = (
            db.query(models.Category.name, func.sum(models.Expense.amount).label("total"))
            .join(models.Expense, models.Expense.category_id == models.Category.id)
            .filter(
                models.Expense.user_id == user_id,
                models.Expense.date >= date_from,
                models.Expense.date <= date_to,
            )
            .group_by(models.Category.id)
            .order_by(func.sum(models.Expense.amount).desc())
            .limit(limit)
            .all()
        )
        result = [{"category": r.name, "total": round(r.total, 2)} for r in rows]
        return json.dumps(result, ensure_ascii=False)

    return json.dumps({"error": f"Unknown tool: {name}"})


# ─────────────────────────── SYSTEM PROMPT ───────────────────────────

SYSTEM_PROMPT = """You are a smart personal finance assistant built into the FinTrack expense tracking app.
You help users manage their expenses through natural conversation.

You CAN:
- Add new expenses (use add_expense tool)
- Show spending summaries for any period (use get_spending_summary)
- List recent expenses (use list_expenses)
- Show category breakdown (use list_categories, get_top_categories)
- Answer questions about spending habits

Rules:
- Always respond in the SAME LANGUAGE the user writes in
- Be concise — short, clear answers
- When adding an expense, confirm what you added (amount, description, category, date)
- Format amounts with 2 decimal places and the appropriate currency symbol
- Today's date is {today}
- When the user asks about "today", "this week", "this month" — use the corresponding period
"""


# ─────────────────────────── ENDPOINT ───────────────────────────

@router.post("")
async def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI chat is not configured")

    client = OpenAI(api_key=api_key)

    system_msg = SYSTEM_PROMPT.replace("{today}", str(date.today()))
    messages = [{"role": "system", "content": system_msg}]
    messages += [{"role": m.role, "content": m.content} for m in req.messages]

    # Agentic loop — allow up to 5 tool call rounds
    for _ in range(5):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        # No tool calls — return final answer
        if not msg.tool_calls:
            return {"reply": msg.content, "action": None}

        # Execute tool calls
        messages.append(msg)  # assistant message with tool_calls
        actions = []

        for tc in msg.tool_calls:
            args   = json.loads(tc.function.arguments)
            result = execute_tool(tc.function.name, args, current_user.id, db)

            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      result,
            })

            # Track actions for frontend (to trigger UI refresh)
            if tc.function.name == "add_expense":
                actions.append({"type": "expense_added", "data": json.loads(result)})

    return {"reply": "Sorry, I could not complete the request.", "action": None}
