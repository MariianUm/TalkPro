from fastapi import HTTPException

def raise_400(detail: str):
    raise HTTPException(status_code=400, detail=detail)

def raise_500(detail: str = "Internal server error"):
    raise HTTPException(status_code=500, detail=detail)