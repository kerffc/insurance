"""CSV upload router."""

import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from config import ALLOWED_CSV_EXTENSIONS
from deps import get_current_user
from services.csv_service import parse_csv

router = APIRouter()


@router.post("/upload-clients")
async def upload_clients(
    file: UploadFile = File(...),
    username: str = Depends(get_current_user),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_CSV_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Only CSV files are allowed (got {ext})")

    content = (await file.read()).decode("utf-8-sig")
    result = parse_csv(content)

    if result["errors"] and not result["clients"]:
        raise HTTPException(status_code=400, detail={"errors": result["errors"]})

    return result
