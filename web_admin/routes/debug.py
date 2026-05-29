from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
async def debug_info(request: Request):
    return {"message": "Debug endpoint"}
