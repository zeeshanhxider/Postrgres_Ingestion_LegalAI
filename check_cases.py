#!/usr/bin/env python3
"""Quick check of ingested cases."""
import psycopg2

conn = psycopg2.connect('postgresql://postgres:localdev@localhost:5435/cases_llama3_3')
cur = conn.cursor()

print('=== 3 TEST CASES SUMMARY ===\n')

cur.execute('''
    SELECT c.case_id, c.title, c.docket_number, co.court as court_name,
           (SELECT COUNT(*) FROM case_chunks WHERE case_id = c.case_id) as chunks,
           (SELECT COUNT(*) FROM case_sentences WHERE case_id = c.case_id) as sentences,
           (SELECT COUNT(*) FROM embeddings WHERE case_id = c.case_id) as embeddings,
           (SELECT COUNT(*) FROM case_phrases WHERE case_id = c.case_id) as phrases
    FROM cases c
    LEFT JOIN courts_dim co ON c.court_id = co.court_id
    ORDER BY c.case_id
''')

for row in cur.fetchall():
    title = row[1][:50] + '...' if row[1] and len(row[1]) > 50 else row[1]
    print(f'Case {row[0]}: {title}')
    print(f'  Docket: {row[2]}')
    print(f'  Court: {row[3]}')
    print(f'  RAG: {row[4]} chunks, {row[5]} sentences, {row[6]} embeddings, {row[7]} phrases')
    print()

conn.close()
