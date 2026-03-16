from pymongo import MongoClient
import time
import uuid

# Updated connection string for the Atlas Local image
mongo_client = MongoClient("mongodb://localhost:27017/?directConnection=true")
users_col = mongo_client["social_prod"]["users"]

# Create deterministic IDs
target_user_id = str(uuid.uuid4())
friend_1 = str(uuid.uuid4())
friend_2 = str(uuid.uuid4())

print("--- APP SIMULATOR STARTING ---")

# ACTION 1: Insert a new user
print("\n1. App Action: User signs up.")
users_col.insert_one({
    "_id": target_user_id,
    "name": "Jane Doe",
    "following_ids": []
})
time.sleep(4) 

# ACTION 2: User follows someone
print("\n2. App Action: User follows Friend 1.")
users_col.update_one(
    {"_id": target_user_id},
    {"$push": {"following_ids": friend_1}}
)
time.sleep(4)

# ACTION 3: User follows another person
print("\n3. App Action: User follows Friend 2.")
users_col.update_one(
    {"_id": target_user_id},
    {"$push": {"following_ids": friend_2}}
)
time.sleep(4)

# ACTION 4: User deletes their account
print("\n4. App Action: User deletes their account.")
users_col.delete_one({"_id": target_user_id})

print("\n--- APP SIMULATOR FINISHED ---")
