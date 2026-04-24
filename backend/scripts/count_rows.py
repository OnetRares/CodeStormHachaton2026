import sqlite3
conn=sqlite3.connect('backend/data/discipline_new.db')
cur=conn.cursor()
print('fisa count:', cur.execute('SELECT COUNT(*) FROM fisa_discipline').fetchone()[0])
print('plan count:', cur.execute('SELECT COUNT(*) FROM plan_discipline').fetchone()[0])
print('sectiuni count:', cur.execute('SELECT COUNT(*) FROM fisa_sectiuni').fetchone()[0])
print('sample ids:', cur.execute('SELECT id FROM fisa_discipline ORDER BY id LIMIT 10').fetchall())
conn.close()
