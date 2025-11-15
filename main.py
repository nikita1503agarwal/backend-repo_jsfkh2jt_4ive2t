from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from dateutil.relativedelta import relativedelta
from bson import ObjectId

from schemas import Customer, Item, PawnTicket, CreatePawnRequest, PaymentRequest
from database import db, create_document, get_documents

app = FastAPI(title="Pegadaian API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RedeemRequest(BaseModel):
    ticket_id: str
    amount: float


@app.get("/test")
async def test():
    # try a simple round-trip to DB
    try:
        _ = db["health"].insert_one({"ok": True, "ts": datetime.utcnow()})
    except Exception as e:
        return {"status": "db_error", "detail": str(e)}
    return {"status": "ok"}


def _oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def _calc_months_elapsed(start: datetime, now: Optional[datetime] = None) -> int:
    now = now or datetime.utcnow()
    if now < start:
        return 0
    rd = relativedelta(now, start)
    months = rd.years * 12 + rd.months + (1 if rd.days > 0 else 0)
    return max(0, months)


def _ticket_outstanding(ticket: Dict[str, Any]) -> Dict[str, float]:
    principal = ticket["principal"]
    rate = ticket["monthly_interest_rate"]
    start_date = ticket["start_date"]
    if isinstance(start_date, str):
        start_date = datetime.fromisoformat(start_date)
    months = _calc_months_elapsed(start_date)
    interest = round(principal * rate * months, 2)
    # Sum payments so far
    payments = list(db["payment"].find({"ticket_id": str(ticket["_id"])}))
    paid = sum(p.get("amount", 0) for p in payments)
    total_due = principal + interest
    outstanding = round(max(0.0, total_due - paid), 2)
    return {
        "months": months,
        "interest": round(interest, 2),
        "paid": round(paid, 2),
        "total_due": round(total_due, 2),
        "outstanding": outstanding,
    }


@app.post("/tickets")
async def create_ticket(payload: CreatePawnRequest):
    # Create or upsert customer and item, then ticket
    customer_dict = payload.customer.model_dump()
    item_dict = payload.item.model_dump()

    customer_id = create_document("customer", customer_dict)
    item_id = create_document("item", item_dict)

    start = datetime.utcnow()
    due = start + relativedelta(months=+payload.tenor_months)

    ticket_data = {
        "customer_id": customer_id,
        "item_id": item_id,
        "principal": payload.principal,
        "monthly_interest_rate": payload.monthly_interest_rate,
        "start_date": start,
        "due_date": due,
        "status": "active",
    }
    ticket_id = create_document("pawnticket", ticket_data)
    ticket = db["pawnticket"].find_one({"_id": _oid(ticket_id)})
    ticket["_id"] = str(ticket["_id"])
    return {"ticket": ticket, "message": "Tiket gadai berhasil dibuat"}


@app.get("/tickets")
async def list_tickets(status: Optional[str] = None, limit: int = 50):
    filt: Dict[str, Any] = {}
    if status:
        filt["status"] = status
    tickets = get_documents("pawnticket", filt, limit)
    # enrich minimal info
    for t in tickets:
        cust = db["customer"].find_one({"_id": _oid(t["customer_id"])})
        item = db["item"].find_one({"_id": _oid(t["item_id"])})
        if cust:
            t["customer_name"] = cust.get("name")
            t["phone"] = cust.get("phone")
        if item:
            t["item_category"] = item.get("category")
            t["item_desc"] = item.get("description")
        t["finance"] = _ticket_outstanding({**t, "_id": t["_id"], "start_date": t["start_date"]})
    return {"tickets": tickets}


@app.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: str):
    t = db["pawnticket"].find_one({"_id": _oid(ticket_id)})
    if not t:
        raise HTTPException(404, "Ticket not found")
    t["_id"] = str(t["_id"])
    cust = db["customer"].find_one({"_id": _oid(t["customer_id"])})
    item = db["item"].find_one({"_id": _oid(t["item_id"])})
    finance = _ticket_outstanding(t)
    return {"ticket": t, "customer": cust, "item": item, "finance": finance}


@app.post("/payments")
async def make_payment(payload: PaymentRequest):
    t = db["pawnticket"].find_one({"_id": _oid(payload.ticket_id)})
    if not t:
        raise HTTPException(404, "Ticket not found")
    if t.get("status") != "active":
        raise HTTPException(400, "Ticket tidak aktif")

    pay_id = create_document(
        "payment",
        {"ticket_id": payload.ticket_id, "amount": payload.amount},
    )
    # Check if fully paid
    finance = _ticket_outstanding(t)
    if finance["outstanding"] <= 0.01:
        db["pawnticket"].update_one({"_id": _oid(payload.ticket_id)}, {"$set": {"status": "redeemed", "updated_at": datetime.utcnow()}})
    return {"payment_id": pay_id, "message": "Pembayaran tercatat", "finance": _ticket_outstanding(t)}


@app.post("/tickets/{ticket_id}/redeem")
async def redeem(ticket_id: str):
    t = db["pawnticket"].find_one({"_id": _oid(ticket_id)})
    if not t:
        raise HTTPException(404, "Ticket not found")
    if t.get("status") != "active":
        raise HTTPException(400, "Ticket tidak aktif")
    finance = _ticket_outstanding(t)
    if finance["outstanding"] > 0:
        raise HTTPException(400, f"Masih ada tunggakan Rp{finance['outstanding']}")
    db["pawnticket"].update_one({"_id": _oid(ticket_id)}, {"$set": {"status": "redeemed", "updated_at": datetime.utcnow()}})
    return {"message": "Tiket berhasil ditebus"}


@app.post("/tickets/{ticket_id}/default")
async def mark_default(ticket_id: str):
    t = db["pawnticket"].find_one({"_id": _oid(ticket_id)})
    if not t:
        raise HTTPException(404, "Ticket not found")
    db["pawnticket"].update_one({"_id": _oid(ticket_id)}, {"$set": {"status": "defaulted", "updated_at": datetime.utcnow()}})
    return {"message": "Tiket ditandai wanprestasi"}
