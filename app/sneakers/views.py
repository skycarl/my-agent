from loguru import logger
from fastapi import Depends, APIRouter
from app.core.auth import verify_token
from app.sneakers.schema import SneakerSchema


router = APIRouter(dependencies=[Depends(verify_token)])


@router.get("/sneakers", status_code=200)
async def get_sneakers():
    """
    gets all the sneakers listed in the database.

    Returns:
        list: An array of sneakers' objects.
    """

    return [
        {
            "id": 1,
            "brand_name": "Nike",
            "name": "Air Max",
            "description": "Comfortable running shoes",
            "size": 10,
            "color": "Black",
            "free_delivery": True,
        }
    ]


@router.post("/sneakers", status_code=201)
async def add_sneaker(payload: SneakerSchema):
    """
    Add sneaker in the database.

    Returns:
        Object: same payload which was sent with 201 status code on success.
    """

    logger.success("Added a sneaker.")
    return payload


@router.put("/sneakers/{sneaker_id}", status_code=201)
async def update_sneaker(sneaker_id: int, payload: SneakerSchema):
    """
    Updates the sneaker object in db

    Raises:
        HTTPException: 404 if sneaker id is not found in the db

    Returns:
        object: updated sneaker object with 201 status code
    """

    logger.success("Updated a sneaker.")
    return {"id": sneaker_id, **payload.dict()}


@router.delete("/sneakers/{sneaker_id}", status_code=204)
async def delete_sneaker(sneaker_id: int):
    """
    Deletes the sneaker object from db

    Raises:
        HTTPException: 404 if sneaker id is not found in the db

    Returns:
        Object: Deleted true with 204 status code
    """

    logger.success("Deleted a sneaker.")

    return {"Deleted": True}
