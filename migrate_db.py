import sqlite3
import pandas as pd
from datetime import datetime

conn = sqlite3.connect('salary_reviews.db')
c = conn.cursor()

# 1. Add sr_no column if it doesn't exist
try:
    c.execute("ALTER TABLE salary_reviews ADD COLUMN sr_no INTEGER")
    print("Added sr_no column.")
except sqlite3.OperationalError as e:
    print("Column might already exist:", e)

# 2. Read excel file
file_path = r'C:\Users\testuser\Downloads\Salary_Review_Template_updated_v25 Esh2.xlsx'
df = pd.read_excel(file_path, sheet_name='Salary Reviews')

inserted = 0
for _, row in df.iterrows():
    emp_name = row['Employee Name']
    c.execute("SELECT id FROM employees WHERE name = ?", (emp_name,))
    emp_row = c.fetchone()
    if not emp_row:
        print(f"Employee {emp_name} not found!")
        continue
    emp_id = emp_row[0]
    
    # Parse dates to YYYY-MM-DD
    def parse_date(d):
        if pd.isna(d): return None
        if isinstance(d, datetime): return d.strftime('%Y-%m-%d')
        if isinstance(d, str):
            try: return datetime.strptime(d, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d')
            except: pass
            try: return datetime.strptime(d, '%d-%b-%Y').strftime('%Y-%m-%d')
            except: pass
            # check for ISO format 
            if 'T' in d: return d.split('T')[0]
        return str(d).split(' ')[0]
        
    rev_date = parse_date(row['Review Date'])
    eff_date = parse_date(row['Effective Date'])
    
    prev_sal = row['Previous Salary'] if not pd.isna(row['Previous Salary']) else 0
    inc_amt = row['Increment Amount'] if not pd.isna(row['Increment Amount']) else 0
    new_sal = row['New Salary'] if not pd.isna(row['New Salary']) else 0
    
    inc_pct = (inc_amt / prev_sal * 100) if prev_sal and prev_sal > 0 else 0
    
    status = row['Status'] if not pd.isna(row['Status']) else 'Finalized'
    remark = row['Remark'] if not pd.isna(row['Remark']) else None
    
    # Check if already exists to prevent duplicate (simple check)
    c.execute("SELECT id FROM salary_reviews WHERE employee_id=? AND review_date=? AND new_salary=?", (emp_id, rev_date, new_sal))
    if c.fetchone():
        print(f"Skipping duplicate for {emp_name} on {rev_date}")
        continue
        
    c.execute('''
        INSERT INTO salary_reviews (employee_id, review_name, review_date, previous_salary, increment_amount, increment_percentage, new_salary, effective_date, remark, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (emp_id, row['Review Label'], rev_date, prev_sal, inc_amt, inc_pct, new_sal, eff_date, remark, status))
    inserted += 1

conn.commit()
print(f"Inserted {inserted} rows.")
conn.close()
