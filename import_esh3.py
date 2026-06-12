import sqlite3
import pandas as pd
from datetime import datetime
import os

db_path = "salary_reviews.db"
excel_path = r"C:\Users\testuser\Downloads\Salary_Review_Template_updated_v25 Esh3.xlsx"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Import missing employees
df_emp = pd.read_excel(excel_path, sheet_name='Employees')
for idx, row in df_emp.iterrows():
    name = row['Name']
    if pd.isna(name):
        continue
    name = str(name).strip()
    cursor.execute("SELECT id FROM employees WHERE name = ?", (name,))
    if not cursor.fetchone():
        dept = str(row['Department']) if pd.notna(row['Department']) else ""
        
        # Support flexible date of joining headers
        doj_raw = None
        for col in ['Date of Joining', 'Start Date', 'DOJ', 'date_of_joining', 'start_date']:
            if col in row:
                doj_raw = row[col]
                break
        
        doj_str = ""
        if pd.notna(doj_raw):
            try:
                if isinstance(doj_raw, datetime):
                    doj_str = doj_raw.strftime('%Y-%m-%d')
                else:
                    doj_str = pd.to_datetime(doj_raw).strftime('%Y-%m-%d')
            except Exception:
                pass
                
        # Support flexible role headers
        role = None
        for col in ['Role', 'role']:
            if col in row:
                role = str(row[col]).strip() if pd.notna(row[col]) else None
                break
                
        salary = float(row['Joining Salary']) if pd.notna(row['Joining Salary']) else 0.0
        status = str(row['Status']) if pd.notna(row['Status']) else "Active"
        cursor.execute("""
            INSERT INTO employees (name, department, date_of_joining, role, joining_salary, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, dept, doj_str, role, salary, status))
        print(f"Added employee: {name}")

conn.commit()

# 2. Import Salary Reviews
df_rev = pd.read_excel(excel_path, sheet_name='Salary Reviews')
for idx, row in df_rev.iterrows():
    emp_name = row['Employee Name']
    if pd.isna(emp_name):
        continue
    emp_name = str(emp_name).strip()
    
    cursor.execute("SELECT id FROM employees WHERE name = ?", (emp_name,))
    emp_row = cursor.fetchone()
    if not emp_row:
        print(f"Still not found employee: {emp_name}")
        continue
    
    emp_id = emp_row[0]
    
    label = str(row['Review Label']) if pd.notna(row['Review Label']) else ""
    r_date = row['Review Date']
    if pd.notna(r_date):
        if isinstance(r_date, datetime): r_date = r_date.strftime('%Y-%m-%d')
        else: r_date = pd.to_datetime(r_date).strftime('%Y-%m-%d')
    else: r_date = ""
        
    e_date = row['Effective Date']
    if pd.notna(e_date):
        if isinstance(e_date, datetime): e_date = e_date.strftime('%Y-%m-%d')
        else: e_date = pd.to_datetime(e_date).strftime('%Y-%m-%d')
    else: e_date = ""
        
    prev = float(row['Previous Salary']) if pd.notna(row['Previous Salary']) else 0.0
    inc = float(row['Increment Amount']) if pd.notna(row['Increment Amount']) else 0.0
    inc_p = float(row.get('Increment %', 0.0)) if pd.notna(row.get('Increment %')) else 0.0
    if inc_p == 0.0 and prev > 0 and inc > 0: inc_p = inc / prev * 100.0
    new = float(row['New Salary']) if pd.notna(row['New Salary']) else prev + inc
    
    status = str(row['Status']) if pd.notna(row['Status']) else "Finalized"
    rem = str(row['Remark']) if pd.notna(row['Remark']) else ""
    
    # duplicate check
    cursor.execute("""
        SELECT id FROM salary_reviews 
        WHERE employee_id = ? AND review_date = ? AND previous_salary = ? AND increment_amount = ?
    """, (emp_id, r_date, prev, inc))
    if cursor.fetchone():
        print(f"Skipping duplicate review for {emp_name} on {r_date}")
        continue
        
    cursor.execute("""
        INSERT INTO salary_reviews (employee_id, review_name, review_date, previous_salary, increment_amount, increment_percentage, new_salary, effective_date, status, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (emp_id, label, r_date, prev, inc, inc_p, new, e_date, status, rem))
    print(f"Added review for: {emp_name}")

conn.commit()
print("Done!")
