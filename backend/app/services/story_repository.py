import logging
from datetime import datetime
from typing import Dict, Any, Optional
from pymongo import MongoClient
from app.core.config import settings

logger = logging.getLogger(__name__)

class StoryRepository:
    def __init__(self):
        self._memory_store: Dict[str, Dict[str, Any]] = {}
        self.client = None
        self.db = None
        self.collection = None
        
        try:
            client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=1500)
            # Test server connection ping
            client.admin.command('ping')
            self.client = client
            self.db = self.client[settings.MONGODB_DB_NAME]
            self.collection = self.db["stories"]
            logger.info(f"[StoryRepository] Connected to MongoDB database: {settings.MONGODB_DB_NAME}")
        except Exception as e:
            logger.warning(f"[StoryRepository] MongoDB offline/unavailable ({e}). Falling back to seamless in-memory storage.")
            self.client = None
            self.db = None
            self.collection = None

    def save_story_record(self, record: Dict[str, Any]) -> bool:
        """
        Saves or updates story record in MongoDB (or in-memory store fallback).
        """
        story_id = record.get("story_id")
        if not story_id:
            return False

        record["updated_at"] = datetime.utcnow().isoformat()
        if "created_at" not in record:
            record["created_at"] = record["updated_at"]

        # 1. Update in-memory fallback cache
        self._memory_store[story_id] = record

        # 2. Persist to MongoDB if connected
        if self.collection is not None:
            try:
                self.collection.update_one(
                    {"story_id": story_id},
                    {"$set": record},
                    upsert=True
                )
                logger.info(f"[StoryRepository] Saved record {story_id} to MongoDB.")
                return True
            except Exception as e:
                logger.warning(f"[StoryRepository] Failed saving to MongoDB ({e}). Record kept in memory.")
                return True
        else:
            logger.info(f"[StoryRepository] Saved record {story_id} to in-memory store.")
            return True

    def get_story_record(self, story_id: str) -> Optional[Dict[str, Any]]:
        if self.collection is not None:
            try:
                rec = self.collection.find_one({"story_id": story_id}, {"_id": 0})
                if rec:
                    return rec
            except Exception as e:
                logger.warning(f"[StoryRepository] Error reading from MongoDB ({e}). Checking memory store.")
        return self._memory_store.get(story_id)
