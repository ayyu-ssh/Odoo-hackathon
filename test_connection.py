import psycopg

conn = psycopg.connect(
    host="localhost",
    port=5432,
    dbname="assetflow_db",
    user="assetflow_user",
    password="asset241"
)

print("Database connected!")

conn.close()