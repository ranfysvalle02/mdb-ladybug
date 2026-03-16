from pymongo import MongoClient
import ladybug
import time

print("Connecting to MongoDB Atlas Local...")
# Updated connection string for the Atlas Local image
mongo_client = MongoClient("mongodb://localhost:27017/?directConnection=true") 
mongo_db = mongo_client["social_prod"]
users_col = mongo_db["users"]

print("Connecting to local LadybugDB...")
db = ladybug.Database('./local_graph.db')
conn = ladybug.Connection(db)

# Create schema (wrapped in try/except in case it already exists)
try:
    conn.execute("CREATE NODE TABLE User(id STRING, name STRING, PRIMARY KEY (id))")
    conn.execute("CREATE REL TABLE FOLLOWS(FROM User TO User)")
    print("Graph schema created.")
except Exception:
    print("Graph schema already exists.")

# The pipeline to watch for changes
pipeline = [{"$match": {"operationType": {"$in": ["insert", "update", "delete"]}}}]

print("\n🚀 CDC Worker is LIVE. Listening for changes...")

# Keep trying to connect to the change stream
while True:
    try:
        with users_col.watch(pipeline, fullDocument='updateLookup') as stream:
            for change in stream:
                op_type = change["operationType"]
                doc_id = str(change["documentKey"]["_id"])
                print(f"\n[CDC EVENT] -> {op_type.upper()} on user {doc_id}")

                if op_type in ["insert", "update"]:
                    doc = change["fullDocument"]
                    name = doc.get("name", "Unknown")
                    following_ids = doc.get("following_ids", [])

                    # 1. Upsert Node
                    conn.execute(
                        "MERGE (u:User {id: $id}) SET u.name = $name", 
                        parameters={"id": doc_id, "name": name}
                    )
                    print(f"  └─ Graph: Upserted node for '{name}'")

                    # 2. Wipe old edges for this user
                    conn.execute(
                        "MATCH (source:User {id: $id})-[r:FOLLOWS]->() DELETE r", 
                        parameters={"id": doc_id}
                    )

                    # 3. Recreate new edges
                    for target_id in following_ids:
                        conn.execute("""
                            MATCH (source:User {id: $source_id})
                            MERGE (target:User {id: $target_id}) 
                            MERGE (source)-[:FOLLOWS]->(target)
                        """, parameters={"source_id": doc_id, "target_id": str(target_id)})
                    print(f"  └─ Graph: Synced {len(following_ids)} following relationships.")

                elif op_type == "delete":
                    conn.execute(
                        "MATCH (u:User {id: $id}) DETACH DELETE u", 
                        parameters={"id": doc_id}
                    )
                    print("  └─ Graph: Deleted node and severed all relationships.")
                    
    except Exception as e:
        print(f"Stream error or disconnected: {e}. Retrying in 3 seconds...")
        time.sleep(3)
