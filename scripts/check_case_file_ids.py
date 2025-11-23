"""
Script to check case_file_id data in cases and briefs tables
"""
import psycopg2

# Database connection parameters
conn_params = {
    'host': 'localhost',
    'port': 5433,
    'user': 'postgres',
    'password': 'postgres123',
    'database': 'cases_llama3_3'
}

def check_case_file_ids():
    """Check case_file_id data"""
    conn = psycopg2.connect(**conn_params)
    cursor = conn.cursor()
    
    try:
        # Check cases table
        print("Checking cases table...")
        cursor.execute("""
            SELECT 
                COUNT(*) as total_cases,
                COUNT(case_file_id) as cases_with_case_file_id
            FROM cases;
        """)
        cases_stats = cursor.fetchone()
        print(f"  Total cases: {cases_stats[0]}")
        print(f"  With case_file_id: {cases_stats[1]}")
        
        # Sample case_file_ids from cases
        cursor.execute("""
            SELECT case_file_id 
            FROM cases 
            WHERE case_file_id IS NOT NULL 
            LIMIT 10;
        """)
        print("\nSample case_file_ids in cases table:")
        for (case_file_id,) in cursor.fetchall():
            print(f"  - {case_file_id}")
        
        # Check briefs table
        print("\n\nChecking briefs table...")
        cursor.execute("""
            SELECT 
                COUNT(*) as total_briefs,
                COUNT(case_file_id) as briefs_with_case_file_id
            FROM briefs;
        """)
        briefs_stats = cursor.fetchone()
        print(f"  Total briefs: {briefs_stats[0]}")
        print(f"  With case_file_id: {briefs_stats[1]}")
        
        # Sample case_file_ids from briefs
        cursor.execute("""
            SELECT DISTINCT case_file_id 
            FROM briefs 
            WHERE case_file_id IS NOT NULL 
            LIMIT 10;
        """)
        print("\nSample case_file_ids in briefs table:")
        for (case_file_id,) in cursor.fetchall():
            print(f"  - {case_file_id}")
        
        # Check for matches
        print("\n\nChecking for matching case_file_ids...")
        cursor.execute("""
            SELECT COUNT(DISTINCT b.case_file_id)
            FROM briefs b
            INNER JOIN cases c ON b.case_file_id = c.case_file_id;
        """)
        matches = cursor.fetchone()[0]
        print(f"  Matching case_file_ids: {matches}")
        
        # Check if normalization is needed
        cursor.execute("""
            SELECT b.case_file_id, c.case_file_id
            FROM briefs b
            CROSS JOIN cases c
            WHERE normalize_case_file_id(b.case_file_id) = normalize_case_file_id(c.case_file_id)
            LIMIT 5;
        """)
        print("\nWith normalization function:")
        for brief_id, case_id in cursor.fetchall():
            print(f"  Brief: {brief_id} → Case: {case_id}")
        
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    check_case_file_ids()
