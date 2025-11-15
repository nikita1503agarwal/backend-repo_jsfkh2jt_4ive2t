# Lightweight Mongo helper matching platform-provided interface
from typing import Any, Dict, Optional, List
from datetime import datetime
import os
from pymongo import MongoClient

DATABASE_URL = os.environ.get("DATABASE_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "appdb")

_client: Optional[MongoClient] = None

def _get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(DATABASE_URL)
    return _client

@property
def db():
    return _get_client()[DATABASE_NAME]

# Helper to insert with timestamps

def create_document(collection_name: str, data: Dict[str, Any]) -> str:
    now = datetime.utcnow()
    payload = {**data, "created_at": now, "updated_at": now}
    result = db[collection_name].insert_one(payload)
    return str(result.inserted_id)

# Helper to query documents

def get_documents(collection_name: str, filter_dict: Dict[str, Any], limit: int = 50) -> List[Dict[str, Any]]:
    cursor = db[collection_name].find(filter_dict).limit(limit).sort("created_at", -1)
    docs = []
    for d in cursor:
        d["_id"] = str(d["_id"])  # stringify ObjectId
        docs.append(d)
    return docs
