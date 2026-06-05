import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import re

DB_PATH = "salary_reviews.db"
EXCEL_PATH = "Salary_Review_Template_updated_v25.xlsx"
TEMPLATE_PATH = "Salary_Review_Template.xlsx"

def parse_date(val):
    if pd.isna(val) or val is None:
        return None
    if hasattr(val, 'strftime'):
        return val.strftime("%Y-%m-%d")
    val_str = str(val).strip()
    if val_str.lower() in ['n/a', 'no review', 'na', 'none', '', 'no']:
        return None
    
    # Try converting numeric Excel serial
    try:
        val_float = float(val)
        if 30000 < val_float < 60000:
            base_date = datetime(1899, 12, 30)
            dt = base_date + timedelta(days=int(val_float))
            return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass
    
    # Try standard string parsing
    for fmt in ["%d %B %Y", "%Y-%m-%d", "%d-%b-%Y", "%b-%y", "%B-%y", "%Y-%m-%d %H:%M:%S"]:
        try:
            dt = datetime.strptime(val_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
            
    # Try parsing custom formats like "Aug-23" or "Jun 24"
    m = re.match(r"^([A-Za-z]+)[-\s]([0-9]+)$", val_str)
    if m:
        month_str, year_str = m.groups()
        if len(year_str) == 2:
            year_str = "20" + year_str
        for m_fmt in ["%b", "%B"]:
            try:
                dt = datetime.strptime(f"01-{month_str}-{year_str}", f"%d-{m_fmt}-%Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
            
    return val_str

def parse_float(val):
    if pd.isna(val) or val is None:
        return None
    val_str = str(val).strip().replace(",", "")
    if val_str.lower() in ['n/a', 'na', 'none', '', 'resigned', 'no review']:
        return None
    try:
        return float(val_str)
    except ValueError:
        return None

def init_db(force=False):
    if os.path.exists(DB_PATH) and not force:
        print(f"Database already exists at {DB_PATH}. Skipping initialization.")
        return False
        
    print(f"Initializing database at {DB_PATH}...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    if force:
        cursor.execute("PRAGMA foreign_keys = OFF;")
        cursor.execute("DROP TABLE IF EXISTS salary_reviews;")
        cursor.execute("DROP TABLE IF EXISTS employees;")
        cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Create tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        department TEXT DEFAULT 'Tech',
        start_date TEXT,
        joining_salary REAL,
        current_salary REAL,
        last_review_date TEXT,
        last_review_effective_date TEXT,
        status TEXT DEFAULT 'Active'
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS salary_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        review_name TEXT NOT NULL,
        review_date TEXT,
        previous_salary REAL,
        increment_amount REAL,
        increment_percentage REAL,
        new_salary REAL,
        effective_date TEXT,
        remark TEXT,
        status TEXT DEFAULT 'Finalized',
        FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS salary_reviews_archive (
        archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_id INTEGER,
        employee_id INTEGER NOT NULL,
        review_name TEXT NOT NULL,
        review_date TEXT,
        previous_salary REAL,
        increment_amount REAL,
        increment_percentage REAL,
        new_salary REAL,
        effective_date TEXT,
        remark TEXT,
        status TEXT,
        archived_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    conn.commit()
    conn.close()
    return True

def import_new_template(file_path):
    print(f"Seeding from clean template format in {file_path}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    df_emp = pd.read_excel(file_path, sheet_name="Employees")
    df_rev = pd.read_excel(file_path, sheet_name="Salary Reviews")
    
    # Insert employees
    for _, row in df_emp.iterrows():
        name = str(row['Name']).strip()
        dept = str(row['Department']).strip() if 'Department' in df_emp.columns else 'Tech'
        start_date = parse_date(row['Start Date'])
        joining_salary = parse_float(row['Joining Salary'])
        status = str(row['Status']).strip() if 'Status' in df_emp.columns else 'Active'
        
        cursor.execute("""
            INSERT OR REPLACE INTO employees (name, department, start_date, joining_salary, current_salary, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, dept, start_date, joining_salary, joining_salary, status))
        
    # Get employee IDs map
    cursor.execute("SELECT id, name FROM employees")
    emp_map = {name: emp_id for emp_id, name in cursor.fetchall()}
    
    # Insert reviews
    for _, row in df_rev.iterrows():
        emp_name = str(row['Employee Name']).strip()
        if emp_name not in emp_map:
            # Insert employee on-the-fly if missing
            cursor.execute("""
                INSERT INTO employees (name, department, status)
                VALUES (?, 'Tech', 'Active')
            """, (emp_name,))
            emp_map[emp_name] = cursor.lastrowid
            
        emp_id = emp_map[emp_name]
        rev_name = str(row['Review Label']).strip()
        rev_date = parse_date(row['Review Date'])
        eff_date = parse_date(row['Effective Date']) if 'Effective Date' in df_rev.columns else rev_date
        prev_sal = parse_float(row['Previous Salary'])
        inc_amt = parse_float(row['Increment Amount'])
        new_sal = parse_float(row['New Salary'])
        status = str(row['Status']).strip() if 'Status' in df_rev.columns else 'Finalized'
        remark = str(row['Remark']).strip() if 'Remark' in df_rev.columns and not pd.isna(row['Remark']) else None
        
        # Reconstruct values if missing
        if prev_sal is None and new_sal is not None and inc_amt is not None:
            prev_sal = new_sal - inc_amt
        if inc_amt is None and new_sal is not None and prev_sal is not None:
            inc_amt = new_sal - prev_sal
        if new_sal is None and prev_sal is not None and inc_amt is not None:
            new_sal = prev_sal + inc_amt
            
        inc_pct = (inc_amt / prev_sal * 100.0) if prev_sal and inc_amt else 0.0
        
        cursor.execute("""
            INSERT INTO salary_reviews (employee_id, review_name, review_date, previous_salary, increment_amount, increment_percentage, new_salary, effective_date, remark, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (emp_id, rev_name, rev_date, prev_sal, inc_amt, inc_pct, new_sal, eff_date, remark, status))
        
    # Recalculate current_salary for all employees based on last finalized review
    for emp_name, emp_id in emp_map.items():
        cursor.execute("""
            SELECT new_salary FROM salary_reviews 
            WHERE employee_id = ? AND status = 'Finalized' 
            ORDER BY effective_date DESC, id DESC LIMIT 1
        """, (emp_id,))
        last_final_row = cursor.fetchone()
        
        cursor.execute("SELECT joining_salary FROM employees WHERE id = ?", (emp_id,))
        join_sal_row = cursor.fetchone()
        joining_salary = join_sal_row[0] if join_sal_row else 0.0
        
        final_salary = last_final_row[0] if last_final_row else (joining_salary if joining_salary is not None else 0.0)
        cursor.execute("UPDATE employees SET current_salary = ? WHERE id = ?", (final_salary, emp_id))
        
    conn.commit()
    conn.close()
    print("Database import from clean template completed!")

def import_legacy_excel():
    print("Seeding from legacy Excel columns format...")
    df = pd.read_excel(EXCEL_PATH, header=None)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    reviews_mapping = [
        ("Review 2017", 3, 4),
        ("Review 2018", 5, 6),
        ("Review 2019", 7, 8),
        ("Review 2020", 9, 10),
        ("Review 2021", 11, 12),
        ("Review 2022", 13, 14),
        ("Review 23", 15, 16),
        ("Review 24", 17, 18),
        ("Review 2025", 19, 20),
        ("Review-26", 21, 22)
    ]
    
    for col_idx in range(1, df.shape[1]):
        name_val = df.iloc[0, col_idx]
        if pd.isna(name_val) or str(name_val).strip() == "" or str(name_val).strip().startswith("Unnamed:"):
            continue
            
        name = str(name_val).strip()
        start_date = parse_date(df.iloc[1, col_idx])
        joining_salary = parse_float(df.iloc[2, col_idx])
        
        status = 'Active'
        proposed_amt_val = df.iloc[24, col_idx]
        proposed_remark_val = df.iloc[30, col_idx]
        
        if (not pd.isna(proposed_amt_val) and str(proposed_amt_val).strip().lower() == 'resigned') or \
           (not pd.isna(proposed_remark_val) and 'resign' in str(proposed_remark_val).strip().lower()):
            status = 'Resigned'
            
        cursor.execute("""
            INSERT OR REPLACE INTO employees (name, department, start_date, joining_salary, current_salary, status)
            VALUES (?, 'Tech', ?, ?, ?, ?)
        """, (name, start_date, joining_salary, joining_salary, status))
        
        employee_id = cursor.lastrowid
        running_salary = joining_salary
        
        for rev_name, rev_row, sal_row in reviews_mapping:
            rev_date_val = df.iloc[rev_row, col_idx]
            new_sal_val = df.iloc[sal_row, col_idx]
            
            rev_date = parse_date(rev_date_val)
            new_salary = parse_float(new_sal_val)
            
            if running_salary is None and new_salary is not None:
                running_salary = new_salary
                cursor.execute("UPDATE employees SET joining_salary = ? WHERE id = ?", (running_salary, employee_id))
            
            if new_salary is None:
                if rev_date is not None:
                    cursor.execute("""
                        INSERT INTO salary_reviews (employee_id, review_name, review_date, previous_salary, increment_amount, increment_percentage, new_salary, effective_date, status)
                        VALUES (?, ?, ?, ?, 0.0, 0.0, ?, ?, 'Finalized')
                    """, (employee_id, rev_name, rev_date, running_salary, running_salary, rev_date))
                continue
                
            if rev_date is not None or new_salary != running_salary:
                prev_salary = running_salary if running_salary is not None else new_salary
                increment_amount = new_salary - prev_salary
                increment_percentage = (increment_amount / prev_salary * 100.0) if prev_salary and prev_salary > 0 else 0.0
                
                if rev_date is None:
                    yr_match = re.search(r"\b(20\d{2}|\d{2})\b", rev_name)
                    if yr_match:
                        yr = yr_match.group(1)
                        if len(yr) == 2:
                            yr = "20" + yr
                        rev_date = f"{yr}-04-01"
                        
                cursor.execute("""
                    INSERT INTO salary_reviews (employee_id, review_name, review_date, previous_salary, increment_amount, increment_percentage, new_salary, effective_date, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Finalized')
                """, (employee_id, rev_name, rev_date, prev_salary, increment_amount, increment_percentage, new_salary, rev_date))
                
                running_salary = new_salary
                
        proposed_new_sal = parse_float(df.iloc[23, col_idx])
        proposed_amt_str = df.iloc[24, col_idx]
        proposed_amt_num = parse_float(df.iloc[25, col_idx])
        proposed_percent = parse_float(df.iloc[26, col_idx])
        proposed_eff_date = parse_date(df.iloc[27, col_idx])
        proposed_curr_sal = parse_float(df.iloc[29, col_idx])
        proposed_remark = str(df.iloc[30, col_idx]).strip() if not pd.isna(df.iloc[30, col_idx]) else None
        
        if (proposed_new_sal is not None or proposed_amt_num is not None) and status == 'Active':
            prev_salary = proposed_curr_sal if proposed_curr_sal is not None else running_salary
            new_salary = proposed_new_sal if proposed_new_sal is not None else (prev_salary + (proposed_amt_num or 0))
            
            inc_amount = proposed_amt_num if proposed_amt_num is not None else (new_salary - prev_salary)
            inc_percent = proposed_percent * 100.0 if proposed_percent is not None else ((inc_amount / prev_salary * 100.0) if prev_salary else 0.0)
            
            cursor.execute("""
                INSERT INTO salary_reviews (employee_id, review_name, review_date, previous_salary, increment_amount, increment_percentage, new_salary, effective_date, remark, status)
                VALUES (?, 'Review-27', ?, ?, ?, ?, ?, ?, ?, 'Proposed')
            """, (employee_id, proposed_eff_date, prev_salary, inc_amount, inc_percent, new_salary, proposed_eff_date, proposed_remark))
            
        cursor.execute("SELECT new_salary FROM salary_reviews WHERE employee_id = ? AND status = 'Finalized' ORDER BY id DESC LIMIT 1", (employee_id,))
        last_final_row = cursor.fetchone()
        final_salary = last_final_row[0] if last_final_row else (joining_salary if joining_salary is not None else 0.0)
        
        cursor.execute("UPDATE employees SET current_salary = ? WHERE id = ?", (final_salary, employee_id))
        
    conn.commit()
    conn.close()
    print("Database seeding from legacy Excel completed successfully!")

def check_and_import():
    # If Book1.xlsx doesn't exist, try to fall back to the Template sheet
    target_file = EXCEL_PATH
    if not os.path.exists(target_file):
        if os.path.exists(TEMPLATE_PATH):
            target_file = TEMPLATE_PATH
        else:
            print("No Excel files (Book1.xlsx or Salary_Review_Template.xlsx) found. Cannot import.")
            return

    try:
        xls = pd.ExcelFile(target_file)
        if "Employees" in xls.sheet_names and "Salary Reviews" in xls.sheet_names:
            init_db(force=True)
            import_new_template(target_file)
        else:
            if target_file == EXCEL_PATH:
                init_db(force=True)
                import_legacy_excel()
            else:
                print("Template file has incorrect worksheets. Skipping seed.")
    except Exception as e:
        print(f"Error checking Excel file: {e}. Defaulting to legacy import if available.")
        if os.path.exists(EXCEL_PATH):
            init_db(force=True)
            import_legacy_excel()

if __name__ == "__main__":
    check_and_import()
