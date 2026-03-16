# mdb-ladybug

---

# The Real-Time AI Knowledge Graph: Escaping the Limitations of a Single Database

If you are building an AI agent that actually needs to understand the world, you eventually realize that basic search isn't enough. You need context. You need a **Knowledge Graph**.

Most developers start by using an LLM to extract entities (like "Elon Musk" and "SpaceX") from their documents and store them in a database like MongoDB. They might even use MongoDB's native `$graphLookup` to connect the dots. For a prototype, this is a brilliant, elegant solution. It works right out of the box.

But then, your app gets popular.

Your Knowledge Graph scales to 50 million nodes. Your AI needs to traverse five hops deep to answer a complex question (e.g., *"Find the competitors of the companies founded by people who used to work with Steve Jobs"*). Suddenly, MongoDB’s `$graphLookup` hits its 100MB RAM limit. Your queries crash, or they spill to disk and your AI takes 120 seconds to generate a single response. Worse, doing heavy graph math on your production database starves your main application of compute power, slowing the app down for everyone else.

The solution isn't to abandon MongoDB. The solution is **Polyglot Persistence**—using the absolute best tool for each specific job.

We are going to let MongoDB be our ultra-reliable document Vault, and we are going to let a lightning-fast, embedded graph database called **LadybugDB** act as our AI's reflexes.

Here is how you build a decoupled, real-time AI Knowledge Graph architecture.

---

## The Value Proposition

Why go through the effort of adding an embedded graph database and a Change Data Capture (CDC) pipeline to your app?

1. **Lightning-Fast AI Responses:** LadybugDB is an embedded, columnar database. It lives right inside your application's memory. There are no network round-trips to a remote database server. Multi-hop queries that take seconds in a document database take milliseconds in LadybugDB.
2. **Total Production Isolation:** Your AI agents can run massive, complex graph algorithms (like PageRank or Shortest Path) on the local LadybugDB file without stealing a single CPU cycle from your production MongoDB cluster. Your main app stays fast.
3. **Resilience and Simplicity:** Because the graph database is just a local `.db` file acting as a "materialized view" of your Mongo data, it is disposable. If the graph gets corrupted, you just delete the file and let MongoDB rebuild it. MongoDB remains your absolute Source of Truth.
4. **Scale:** You bypass MongoDB's 100MB aggregation pipeline memory limits entirely, allowing your AI to traverse massive graphs with zero bottlenecks.

---

## The Architecture: A Biological Metaphor

To understand how this system works, it helps to think of it like a biological system. We are breaking our architecture into four distinct parts:

### 1. The Brain (Extraction)

You have raw, messy text (articles, chat logs, bios). We use an LLM (like OpenAI's GPT-4o-mini) as the "Brain" to read that text and extract structured Nodes (Entities) and Edges (Relationships).

* *Example:* The Brain reads "Steve Jobs founded Apple," and outputs a structured JSON connecting the Person "Steve Jobs" to the Company "Apple" via the "Founded" relationship.

### 2. The Vault (Storage)

Once the Brain extracts that structured JSON, we store it in **MongoDB**. MongoDB is our Vault. It is unmatched at safely storing massive amounts of flexible, hierarchical data. We don't do complex math here; we just safely store the raw records of who is connected to whom.

### 3. The Nervous System (Change Data Capture)

We need a way to get data from the Vault to our AI instantly. We use a background worker script to listen to **MongoDB Change Streams**. This is our Nervous System. Whenever a new relationship is saved in MongoDB, this worker instantly "feels" the change and pushes that new connection into our local graph database.

### 4. The Reflexes (Retrieval & Generation)

When a user actually asks the AI a question, the application doesn't talk to MongoDB at all. Instead, it queries the local **LadybugDB** file. Because it's an embedded graph database built specifically for this math, it acts like a reflex—returning the deep contextual connections in milliseconds. We feed that context to the LLM, and the AI generates a highly accurate, context-aware answer.

---

## Conclusion: Let Databases Do What They Do Best

By decoupling your data ingestion from your AI querying, you create the ultimate setup. Your ingestion scripts can run slowly in the background, carefully building up a massive MongoDB database of knowledge. Meanwhile, your CDC worker silently keeps your graph in sync, and your user-facing AI agent stays incredibly fast and entirely insulated from database lockups.

Let the document database be a document database. Let the graph database do the graph math. Combine them, and your AI becomes unstoppable.

---

## Appendix: The Complete Codebase

If you want to build this right now, here is the complete, production-ready code.

### Prerequisites

You need a MongoDB replica set to use Change Streams. The easiest way to get this locally is using the official Atlas Local Docker image:

```bash
docker run -d -p 27017:27017 --name mongo_prod mongodb/mongodb-atlas-local:latest

```

Install your Python dependencies: `pip install pymongo openai spacy ladybug` (and run `python -m spacy download en_core_web_sm`).

### Script 1: The Brain & The Vault (`1_ingest.py`)

This script reads text, extracts the graph data via OpenAI, and saves it to MongoDB.

```python
import json
from pymongo import MongoClient
from openai import AzureOpenAI

# Connect to the MongoDB Vault
mongo_client = MongoClient("mongodb://localhost:27017/?directConnection=true")
collection = mongo_client["ai_knowledge_base"]["kg_documents"]

az_client = AzureOpenAI(azure_endpoint="YOUR_ENDPOINT", api_version="2023-07-01-preview", api_key="YOUR_KEY")

documents = ["Steve Jobs founded Apple.", "Elon Musk founded SpaceX and Tesla."]

print("🧠 Extracting knowledge and saving to MongoDB Vault...")

for doc in documents:
    prompt = f"Extract nodes and edges from: '{doc}'. Return JSON with 'nodes' and 'relationships' arrays."
    
    response = az_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }
    )
    
    extraction = json.loads(response.choices[0].message.content.strip())
    
    # Store in MongoDB
    for r in extraction.get("relationships", []):
        collection.update_one(
            {"_id": r["source"]},
            {
                "$set": {"type": r.get("source_type", "unknown")},
                "$addToSet": {"edges": {"target": r["target"], "relation": r["relation"]}}
            },
            upsert=True
        )

```

### Script 2: The Nervous System (`2_cdc_worker.py`)

Run this in the background. It watches MongoDB and perfectly mirrors the relationships into LadybugDB in real-time.

```python
from pymongo import MongoClient
import ladybug

mongo_client = MongoClient("mongodb://localhost:27017/?directConnection=true") 
collection = mongo_client["ai_knowledge_base"]["kg_documents"]

# Connect to the local Reflexes (LadybugDB)
db = ladybug.Database('./knowledge_graph.db')
conn = ladybug.Connection(db)

# Setup basic graph schema
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
        
        # 1. Sync Node
        conn.execute("MERGE (n:Entity {id: $id}) SET n.type = $type", 
                     parameters={"id": doc_id, "type": doc.get("type", "unknown")})

        # 2. Wipe old edges (safest way to sync arrays)
        conn.execute("MATCH (source:Entity {id: $id})-[r:RELATES_TO]->() DELETE r", 
                     parameters={"id": doc_id})

        # 3. Sync new edges
        for edge in doc.get("edges", []):
            conn.execute("""
                MATCH (source:Entity {id: $source_id})
                MERGE (target:Entity {id: $target_id}) 
                MERGE (source)-[:RELATES_TO {relation_name: $rel}]->(target)
            """, parameters={"source_id": doc_id, "target_id": edge["target"], "rel": edge["relation"]})

```

### Script 3: The AI Agent (`3_agent.py`)

The user-facing application. Notice it only queries LadybugDB for insane speed, leaving MongoDB completely alone.

```python
import spacy
import ladybug
from openai import AzureOpenAI

nlp = spacy.load("en_core_web_sm")
az_client = AzureOpenAI(azure_endpoint="YOUR_ENDPOINT", api_version="2023-07-01-preview", api_key="YOUR_KEY")

db = ladybug.Database('./knowledge_graph.db')
conn = ladybug.Connection(db)

user_prompt = "Write a short rap about Elon Musk and his companies."

# 1. Figure out who the user is asking about
doc = nlp(user_prompt)
target_person = next((e.text.strip(',.') for e in doc.ents if e.label_ == "PERSON"), "")

# 2. High-Speed Graph Traversal via Cypher (The Reflexes)
cypher_query = """
    MATCH (p:Entity {id: $person})-[r:RELATES_TO*1..2]->(target:Entity)
    RETURN p.id, r[0].relation_name, target.id
"""
results = conn.execute(cypher_query, parameters={"person": target_person})

context_fusion = [f"{row[0]} -> {row[1]} -> {row[2]}" for row in iter(results.get_next, None) if results.has_next() or True]

# 3. Final Answer Generation
msgs = [
    {"role": "system", "content": "You are a helpful AI. Use the provided graph context to inform your response."},
    {"role": "user", "content": f"Graph Context: {context_fusion}\n\nPrompt: {user_prompt}"}
]

response = az_client.chat.completions.create(model="gpt-4o-mini", messages=msgs)
print("\n" + response.choices[0].message.content)

```

---
