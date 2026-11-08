
import time
from fastapi import APIRouter, Query
from sqlalchemy import select, or_

from metadata.database import SessionLocal, StoredObject

router = APIRouter(tags=["Search and Cluster"])


@router.get("/search")
def search_objects(q: str = Query(min_length=1)):
    with SessionLocal() as db:
        objects = db.scalars(
            select(StoredObject)
            .where(
                or_(
                    StoredObject.key.ilike(f"%{q}%"),
                    StoredObject.bucket.ilike(f"%{q}%")
                )
            )
            .order_by(StoredObject.created_at.desc())
            .limit(100)
        ).all()

        return [
            {
                "bucket": obj.bucket,
                "key": obj.key,
                "size": obj.size,
                "version": obj.version
            }
            for obj in objects
        ]
