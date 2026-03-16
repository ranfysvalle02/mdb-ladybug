import json
from pymongo import MongoClient
from openai import AzureOpenAI

# Configuration
MDB_URI = "mongodb://localhost:27017/?directConnection=true"
mongo_client = MongoClient(MDB_URI)
db = mongo_client["ai_knowledge_base"]
collection = db["kg_documents"]

az_client = AzureOpenAI(
    azure_endpoint="YOUR_ENDPOINT",
    api_version="2023-07-01-preview",
    api_key="YOUR_KEY"
)

documents = [
    "Steve Jobs founded Apple.",
    "Before Apple, Steve Jobs worked at Atari.",
    "Elon Musk founded SpaceX and Tesla."
]

print("🧠 Extracting knowledge and saving to MongoDB...")

for doc in documents:
    # 1. Ask LLM to extract JSON (Skipping the massive prompt for brevity, 
    # but using your exact extraction logic)
    prompt = f"Extract nodes and edges from: {doc}. Return JSON with 'nodes' and 'relationships'."
    
    response = az_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }
    )
    
    extraction = json.loads(response.choices[0].message.content.strip())
    
    # 2. Format for MongoDB
    # We create a document for the "Source" node and embed its outgoing edges
    for r in extraction.get("relationships", []):
        doc_id = r["source"]
        
        # Upsert into MongoDB: Create the node if it doesn't exist, and push the new edge
        collection.update_one(
            {"_id": doc_id},
            {
                "$set": {"type": r.get("source_type", "unknown")},
                "$addToSet": {"edges": {"target": r["target"], "relation": r["relation"]}}
            },
            upsert=True
        )
        
print("✅ Raw knowledge secured in MongoDB Vault.")
