from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer, User
from app.schemas import CustomerCreate, CustomerList, CustomerRead, CustomerUpdate
from app.schemas.customer import CustomerStatus, CustomerTier, current_utc_time
from app.services.security import require_roles

router = APIRouter()


def find_customer_conflict(
    db: Session,
    partner_id: str,
    email: str,
    partner_customer_id: str | None = None,
    exclude_customer_id: int | None = None,
) -> Customer | None:
    identity_filters = [Customer.email == email]
    if partner_customer_id:
        identity_filters.append(Customer.partner_customer_id == partner_customer_id)

    statement = select(Customer).where(
        Customer.partner_id == partner_id,
        or_(*identity_filters),
    )
    if exclude_customer_id is not None:
        statement = statement.where(Customer.id != exclude_customer_id)

    return db.scalar(statement)


@router.get("", response_model=CustomerList)
def list_customers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    status_filter: CustomerStatus | None = Query(default=None, alias="status"),
    tier: CustomerTier | None = None,
    partner_id: str | None = None,
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    filters = []
    if status_filter:
        filters.append(Customer.status == status_filter)
    if tier:
        filters.append(Customer.tier == tier)
    if partner_id:
        filters.append(Customer.partner_id == partner_id)

    total_statement = select(func.count()).select_from(Customer).where(*filters)
    total = db.scalar(total_statement) or 0

    statement = (
        select(Customer)
        .where(*filters)
        .order_by(Customer.created_at.desc(), Customer.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    customers = db.scalars(statement).all()

    return {
        "items": customers,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    conflict = find_customer_conflict(
        db,
        partner_id=payload.partner_id,
        partner_customer_id=payload.partner_customer_id,
        email=str(payload.email),
    )
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer already exists for this partner identity.",
        )

    customer = Customer(
        partner_id=payload.partner_id,
        partner_customer_id=payload.partner_customer_id,
        email=str(payload.email),
        name=payload.name,
        status=payload.status,
        tier=payload.tier,
        tags=payload.tags,
        note=payload.note,
        internal_note=payload.internal_note,
        source_updated_at=payload.source_updated_at or current_utc_time(),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(
    customer_id: int,
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )
    return customer


@router.patch("/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    next_partner_id = update_data.get("partner_id", customer.partner_id)
    next_partner_customer_id = update_data.get(
        "partner_customer_id",
        customer.partner_customer_id,
    )
    next_email = str(update_data.get("email", customer.email))

    conflict = find_customer_conflict(
        db,
        partner_id=next_partner_id,
        partner_customer_id=next_partner_customer_id,
        email=next_email,
        exclude_customer_id=customer.id,
    )
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another customer already exists for this partner identity.",
        )

    for field, value in update_data.items():
        if field == "email" and value is not None:
            value = str(value)
        setattr(customer, field, value)

    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: int,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )

    db.delete(customer)
    db.commit()
