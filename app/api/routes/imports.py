from fastapi import APIRouter, File, UploadFile

router = APIRouter()


@router.post("/customers")
async def import_customers(file: UploadFile = File(...)):
    return {
        "filename": file.filename,
        "message": "CSV import will be implemented next",
    }