import psycopg
conn = psycopg.connect("postgresql://auth:authpwd@127.0.0.1:54321/authentication")
with conn, conn.cursor() as cur:
    cur.execute("SELECT enumlabel FROM pg_enum WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname='userrole')")
    print(cur.fetchall())
