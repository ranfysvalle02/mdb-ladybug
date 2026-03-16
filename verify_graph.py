import ladybug

print("Connecting to local LadybugDB...")
db = ladybug.Database('./local_graph.db')
conn = ladybug.Connection(db)

print("\n--- Current Users in Graph ---")
results = conn.execute("MATCH (u:User) RETURN u.name, u.id")
while results.has_next():
    print(results.get_next())

print("\n--- Current Follows Relationships ---")
results = conn.execute("MATCH (a:User)-[:FOLLOWS]->(b:User) RETURN a.name, b.id")
while results.has_next():
    print(results.get_next())
