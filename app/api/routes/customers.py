from fastapi import APIRouter

router = APIRouter()


@router.get("")
def list_customers():
    return {
        "items": [],
        "total": 0,
    }


@router.post("")
def create_customer():
    return {
        "message": "customer creation will be implemented next",
    }