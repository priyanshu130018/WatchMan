import psycopg2

conn = psycopg2.connect(
    "postgresql://postgres.ispjudtokzssjijuyunb:%23app%40pass100@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"
)

print("Connected!")
conn.close()