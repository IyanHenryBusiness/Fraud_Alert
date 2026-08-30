from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db, json_safe

router = APIRouter(prefix="/api", tags=["transactions"])


@router.get("/transactions")
def list_transactions(
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    try:
        query = text(
            """
            SELECT
                t.transaction_id,
                t.customer_id,
                t.business_transaction_id,
                t.transaction_datetime AS transaction_date,
                t.recorded_customer_reference,
                t.amount,
                t.merchant_name,
                t.merchant_category,
                t.channel,
                t.location,
                t.created_at,
                c.customer_id AS customer_customer_id,
                c.customer_reference,
                c.first_name,
                c.last_name,
                c.email,
                c.phone,
                c.date_of_birth,
                c.is_active AS customer_is_active,
                c.created_at AS customer_created_at
            FROM dbo.transactions AS t
            LEFT JOIN dbo.customers AS c
                ON c.customer_id = t.customer_id
            ORDER BY t.transaction_id
            OFFSET :offset ROWS
            FETCH NEXT :limit ROWS ONLY
            """
        )
        rows = db.execute(query, {"offset": offset, "limit": limit}).mappings().all()

        transactions: List[Dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            customer = {
                "customer_id": record.get("customer_customer_id") or record.get("customer_id"),
                "customer_reference": record.get("customer_reference"),
                "first_name": record.get("first_name"),
                "last_name": record.get("last_name"),
                "email": record.get("email"),
                "phone": record.get("phone"),
                "date_of_birth": record.get("date_of_birth"),
                "is_active": record.get("customer_is_active"),
                "created_at": record.get("customer_created_at"),
            }
            transactions.append(
                {
                    "transaction_id": record.get("transaction_id"),
                    "customer_id": record.get("customer_id"),
                    "business_transaction_id": record.get("business_transaction_id"),
                    "recorded_customer_reference": record.get("recorded_customer_reference"),
                    "transaction_date": record.get("transaction_date"),
                    "amount": record.get("amount"),
                    "merchant_name": record.get("merchant_name"),
                    "merchant_category": record.get("merchant_category"),
                    "channel": record.get("channel"),
                    "location": record.get("location"),
                    "created_at": record.get("created_at"),
                    "customer": customer,
                }
            )

        payload = {
            "items": json_safe(transactions),
            "count": len(transactions),
            "limit": limit,
            "offset": offset,
        }
        return payload
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to fetch transaction records.") from exc
