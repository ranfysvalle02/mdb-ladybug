import spacy
import json
import ladybug
from openai import AzureOpenAI

nlp = spacy.load("en_core_web_sm")
az_client = AzureOpenAI(
    azure_endpoint="YOUR_ENDPOINT",
    api_version="2023-07-01-preview",
    api_key="YOUR_KEY"
)

# Connect directly to the local graph file
db = ladybug.Database('./knowledge_graph.db')
conn = ladybug.Connection(db)

# 1. The User's Query
user_prompt = "Write a rap about Elon Musk and his companies."
print(f"User Prompt: {user_prompt}")

# 2. Entity Extraction
doc = nlp(user_prompt)
target_person = ""
for entity in doc.ents:
    if entity.label_ == "PERSON":
        target_person = entity.text.strip(',.')
        break

print(f"🎯 Target Identified: {target_person}")

# 3. High-Speed Graph Traversal (Replacing MongoDB's $graphLookup)
# Cypher query: Find the person, get everything they are related to up to 2 hops away.
cypher_query = """
    MATCH (p:Entity {id: $person})-[r:RELATES_TO*1..2]->(target:Entity)
    RETURN p.id as Source, r[0].relation_name as Relation, target.id as Connection
"""

results = conn.execute(cypher_query, parameters={"person": target_person})

context_fusion = []
while results.has_next():
    row = results.get_next()
    context_fusion.append(f"{row[0]} -> {row[1]} -> {row[2]}")

print(f"🕸️ Graph Context Retrieved in ms: {context_fusion}")

# 4. Final LLM Generation
msgs = [
    {"role": "system", "content": "You are a helpful assistant. Use the provided graph context to inform your response."},
    {"role": "user", "content": f"Context: {context_fusion}"},
    {"role": "user", "content": user_prompt}
]

print("🎤 Rapping...")
ai_response = az_client.chat.completions.create(
    model="gpt-4o-mini",
    messages=msgs
)

print("\n" + ai_response.choices[0].message.content)
