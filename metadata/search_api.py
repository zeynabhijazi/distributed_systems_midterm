
import json
import os
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Column, String, JSON, select

from metadata.database import (
    Base,
    SessionLocal,
    StoredObject,
)

router = APIRouter(tags=["Elasticsearch"])

ES_URL = os.getenv(
    "ELASTICSEARCH_URL",
    "http://localhost:9200",
).rstrip("/")

INDEX = "storage_objects"


class ObjectTag(Base):
    __tablename__ = "object_tags"

    bucket = Column(String(255), primary_key=True)
    key = Column(String(1024), primary_key=True)
    tags = Column(JSON, nullable=False, default=dict)


class TagsRequest(BaseModel):
    tags: dict[str, str]


def check_response(response):
    if response.is_error:
        raise HTTPException(
            503,
            f"Elasticsearch error: {response.text[:300]}",
        )


def get_es_client():
    return httpx.Client(timeout=120.0)


def index_mapping():
    return {
        "mappings": {
            "properties": {
                "bucket": {"type": "keyword"},
                "key": {"type": "keyword"},
                "size": {"type": "long"},
                "version": {"type": "integer"},
                "created_at": {"type": "date"},
                "tags_flat": {"type": "keyword"},
            }
        }
    }


@router.put("/tags/{bucket}/{key:path}")
def set_object_tags(
    bucket: str,
    key: str,
    body: TagsRequest,
):
    if len(body.tags) > 20:
        raise HTTPException(400, "Maximum 20 tags")

    for name, value in body.tags.items():
        if not name or len(name) > 64 or len(value) > 256:
            raise HTTPException(400, "Invalid tag")

    with SessionLocal() as db:
        exists = db.scalar(
            select(StoredObject.id)
            .where(
                StoredObject.bucket == bucket,
                StoredObject.key == key,
            )
            .limit(1)
        )

        if exists is None:
            raise HTTPException(404, "Object not found")

        record = db.get(ObjectTag, (bucket, key))

        if record is None:
            record = ObjectTag(
                bucket=bucket,
                key=key,
                tags=body.tags,
            )
            db.add(record)
        else:
            record.tags = body.tags

        db.commit()

    return {
        "bucket": bucket,
        "key": key,
        "tags": body.tags,
        "message": "Tags saved",
    }


@router.get("/tags/{bucket}/{key:path}")
def get_object_tags(bucket: str, key: str):
    with SessionLocal() as db:
        record = db.get(ObjectTag, (bucket, key))

        return {
            "bucket": bucket,
            "key": key,
            "tags": record.tags if record else {},
        }


@router.post("/search/reindex")
def rebuild_search_index():
    # Rebuild the Elasticsearch index from PostgreSQL.
    # This is a simple synchronization approach for
    # the local exam project.

    with SessionLocal() as db:
        objects = db.scalars(
            select(StoredObject)
            .order_by(StoredObject.id)
        ).all()

        tags = {
            (row.bucket, row.key): row.tags
            for row in db.scalars(select(ObjectTag)).all()
        }

        with get_es_client() as client:
            response = client.get(ES_URL)

            if response.is_error:
                raise HTTPException(
                    503, "Elasticsearch is not ready"
                )

            deletion = client.delete(f"{ES_URL}/{INDEX}")

            if deletion.status_code not in (200, 404):
                check_response(deletion)

            creation = client.put(
                f"{ES_URL}/{INDEX}",
                json=index_mapping(),
            )
            check_response(creation)

            indexed = 0

            for offset in range(0, len(objects), 500):
                batch = objects[offset:offset + 500]
                lines = []

                for obj in batch:
                    object_tags = tags.get(
                        (obj.bucket, obj.key), {}
                    )

                    document = {
                        "bucket": obj.bucket,
                        "key": obj.key,
                        "size": obj.size,
                        "version": obj.version,
                        "created_at": obj.created_at.isoformat(),
                        "tags_flat": [
                            f"{name}={value}"
                            for name, value in object_tags.items()
                        ],
                    }

                    lines.append(json.dumps({
                        "index": {
                            "_index": INDEX,
                            "_id": str(obj.id),
                        }
                    }))
                    lines.append(json.dumps(document))

                payload = "\n".join(lines) + "\n"

                response = client.post(
                    f"{ES_URL}/_bulk",
                    content=payload,
                    headers={
                        "Content-Type": "application/x-ndjson"
                    },
                )
                check_response(response)

                result = response.json()

                if result.get("errors"):
                    raise HTTPException(
                        503, "Some documents failed to index"
                    )

                indexed += len(batch)

            client.post(f"{ES_URL}/{INDEX}/_refresh")

    return {
        "message": "Elasticsearch index rebuilt",
        "indexed_objects": indexed,
    }


@router.get("/search")
def search_objects(
    q: str | None = None,
    prefix: str | None = None,
    bucket: str | None = None,
    min_size: int | None = Query(default=None, ge=0),
    max_size: int | None = Query(default=None, ge=0),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    tag_key: str | None = None,
    tag_value: str | None = None,
):
    if (
        min_size is not None
        and max_size is not None
        and min_size > max_size
    ):
        raise HTTPException(
            400, "min_size cannot exceed max_size"
        )

    if (tag_key is None) != (tag_value is None):
        raise HTTPException(
            400, "Provide both tag_key and tag_value"
        )

    filters = []

    if bucket:
        filters.append({"term": {"bucket": bucket}})

    if prefix:
        filters.append({"prefix": {"key": prefix}})

    if min_size is not None or max_size is not None:
        bounds = {}

        if min_size is not None:
            bounds["gte"] = min_size

        if max_size is not None:
            bounds["lte"] = max_size

        filters.append({"range": {"size": bounds}})

    if date_from or date_to:
        bounds = {}

        if date_from:
            bounds["gte"] = date_from.isoformat()

        if date_to:
            bounds["lte"] = date_to.isoformat()

        filters.append({
            "range": {"created_at": bounds}
        })

    if tag_key is not None:
        filters.append({
            "term": {
                "tags_flat": f"{tag_key}={tag_value}"
            }
        })

    if q:
        # Search for a substring in filename or bucket.
        # Escape wildcard metacharacters supplied by users.
        safe_q = (
            q.replace("\\", "\\\\")
             .replace("*", "\\*")
             .replace("?", "\\?")
        )

        filters.append({
            "bool": {
                "should": [
                    {
                        "wildcard": {
                            "key": {
                                "value": f"*{safe_q}*",
                                "case_insensitive": True,
                            }
                        }
                    },
                    {
                        "wildcard": {
                            "bucket": {
                                "value": f"*{safe_q}*",
                                "case_insensitive": True,
                            }
                        }
                    },
                ],
                "minimum_should_match": 1,
            }
        })

    query = {
        "size": 100,
        "query": {
            "bool": {
                "filter": filters
            }
        },
        "sort": [
            {"created_at": {"order": "desc"}}
        ],
    }

    try:
        with get_es_client() as client:
            response = client.post(
                f"{ES_URL}/{INDEX}/_search",
                json=query,
            )
            check_response(response)
            result = response.json()

    except httpx.HTTPError as error:
        raise HTTPException(
            503, f"Elasticsearch unavailable: {error}"
        )

    return [
        hit["_source"]
        for hit in result["hits"]["hits"]
    ]
