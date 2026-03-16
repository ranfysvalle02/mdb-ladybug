from pymongo import MongoClient
import ladybug
import time

print("🔌 Connecting to MongoDB Atlas Local...")
mongo_client = MongoClient("mongodb://localhost:27017/?directConnection=true") 
collection = mongo_client["ai_knowledge_base"]["kg_documents"]

print("🐞 Connecting to local LadybugDB...")
db = ladybug.Database('./knowledge_graph.db')
conn = ladybug.Connection(db)

# Create our Graph Schema. We use a generic 'RELATES_TO' edge with a property 
# so we don't have to hardcode every possible relationship type.
try:
    conn.execute("CREATE NODE TABLE Entity(id STRING, type STRING, PRIMARY KEY (id))")
    conn.execute("CREATE REL TABLE RELATES_TO(FROM Entity TO Entity, relation_name STRING)")
except Exception:
    pass

pipeline = [{"$match": {"operationType": {"$in": ["insert", "update"]}}}]

print("🚀 CDC Worker is LIVE. Syncing Graph...")

with collection.watch(pipeline, fullDocument='updateLookup') as stream:
    for change in stream:
        doc = change["fullDocument"]
        doc_id = str(doc["_id"])
        node_type = doc.get("type", "unknown")
        edges = doc.get("edges", [])

        # 1. Upsert the Node in Ladybug
        conn.execute(
            "MERGE (n:Entity {id: $id}) SET n.type = $type", 
            parameters={"id": doc_id, "type": node_type}
        )

        # 2. Wipe old edges to prevent duplicates on array updates
        conn.execute(
            "MATCH (source:Entity {id: $id})-[r:RELATES_TO]->() DELETE r", 
            parameters={"id": doc_id}
        )

        # 3. Write the new relationships
        for edge in edges:
            conn.execute("""
                MATCH (source:Entity {id: $source_id})
                MERGE (target:Entity {id: $target_id}) 
                MERGE (source)-[:RELATES_TO {relation_name: $rel}]->(target)
            """, parameters={
                "source_id": doc_id, 
                "target_id": edge["target"],
                "rel": edge["relation"]
            })
            
        print(f"🔄 Synced {doc_id} with {len(edges)} relationships to LadybugDB.")
