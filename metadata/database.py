
import os
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    BigInteger,
    DateTime,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://storageuser:storagepass@localhost:5432/storagedb",
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()


# ----------------------------------------
# OBJECT METADATA
# ----------------------------------------

class StoredObject(Base):
    __tablename__ = "objects"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    bucket = Column(String(255), nullable=False)
    key = Column(String(1024), nullable=False)
    size = Column(BigInteger, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    chunk_hashes = Column(JSON, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "bucket",
            "key",
            "version",
            name="uq_object_version",
        ),
    )


# ----------------------------------------
# REPLICATION REFERENCES
# ----------------------------------------

class ChunkReference(Base):
    __tablename__ = "chunk_references"

    id = Column(Integer, primary_key=True)

    object_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    chunk_index = Column(Integer, nullable=False)

    chunk_hash = Column(
        String(64),
        nullable=False,
        index=True,
    )

    nodes = Column(JSON, nullable=False)


# ----------------------------------------
# DEDUPLICATED REPLICATED CHUNKS
# ----------------------------------------

class StoredChunk(Base):
    __tablename__ = "stored_chunks"

    hash = Column(
        String(64),
        primary_key=True,
    )

    size = Column(BigInteger, nullable=False)

    ref_count = Column(
        Integer,
        default=0,
        nullable=False,
    )

    nodes = Column(JSON, nullable=False)


# ----------------------------------------
# BUCKETS
# ----------------------------------------

class Bucket(Base):
    __tablename__ = "buckets"

    name = Column(
        String(255),
        primary_key=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ----------------------------------------
# BUCKET STORAGE POLICIES
# ----------------------------------------

class BucketStoragePolicy(Base):
    __tablename__ = "bucket_storage_policies"

    bucket = Column(
        String(255),
        primary_key=True,
    )

    mode = Column(
        String(20),
        nullable=False,
        default="replication",
    )


# ----------------------------------------
# ERASURE-CODED CHUNK MANIFESTS
# ----------------------------------------

class ErasureChunk(Base):
    __tablename__ = "erasure_chunks"

    id = Column(
        Integer,
        primary_key=True,
    )

    object_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    chunk_index = Column(
        Integer,
        nullable=False,
    )

    original_hash = Column(
        String(64),
        nullable=False,
    )

    original_size = Column(
        BigInteger,
        nullable=False,
    )

    # Stores the six shard indices, hashes and nodes.
    shards = Column(JSON, nullable=False)


class ErasureShard(Base):
    __tablename__ = "erasure_shards"

    hash = Column(
        String(64),
        primary_key=True,
    )

    ref_count = Column(
        Integer,
        nullable=False,
        default=0,
    )

    nodes = Column(JSON, nullable=False)




def init_db():
    Base.metadata.create_all(bind=engine)
