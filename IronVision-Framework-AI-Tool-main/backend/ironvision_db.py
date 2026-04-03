"""
IronVision Atlas Database Connection
Connects to IronVision's MongoDB Atlas for Policy Builder data.
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient

IRONVISION_MONGO_URI = os.environ.get("IRONVISION_MONGO_URI", "")
IRONVISION_DB_NAME = os.environ.get("IRONVISION_DB_NAME", "ironvision")

iv_client = None
iv_db = None


def get_ironvision_db():
    global iv_client, iv_db
    if iv_db is not None:
        return iv_db
    if not IRONVISION_MONGO_URI:
        return None
    iv_client = AsyncIOMotorClient(IRONVISION_MONGO_URI)
    iv_db = iv_client[IRONVISION_DB_NAME]
    return iv_db


def close_ironvision_db():
    global iv_client
    if iv_client:
        iv_client.close()
