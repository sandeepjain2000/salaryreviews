import os
import shutil
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "salary_reviews.db"
BACKUP_PATH = "salary_reviews.db.bak"
EXCEL_PATH = r"C:\Users\sandeep\Downloads\Claudes\SalaryReview\Proposed Salary Reviews-PuneTeam-DoJ.xlsx"

def parse_date(val):
    if pd.isna(val) or val is None:
        return None
    if hasattr(val, 'strftime'):
        return val.strftime("%Y-%m-%d")
    val_str = str(val).strip()
    if val_str.lower() in ['n/a', 'na', 'none', '', 'no']:
        return None
    
    # Try standard formats
    for fmt in ["%d %B %Y", "%Y-%m-%d", "%d-%b-%Y", "%b-%y", "%B-%y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"]:
        try:
            dt = datetime.strptime(val_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    try:
        dt = pd.to_datetime(val_str)
        return dt.strftime("%Y-%m-%d")
    except:
        pass
    return val_str

def migrate():
    # 1. Backup the database
    if os.path.exists(DB_PATH):
        print(f"Creating database backup at {BACKUP_PATH}...")
        shutil.copy2(DB_PATH, BACKUP_PATH)
    else:
        print(f"[ERROR] Database {DB_PATH} not found. Cannot migrate.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Disable foreign keys temporarily during schema switch
    cursor.execute("PRAGMA foreign_keys = OFF;")

    # Check columns in employees table
    cursor.execute("PRAGMA table_info(employees)")
    cols = [col[1] for col in cursor.fetchall()]

    if "start_date" in cols:
        print("Migrating schema to rename 'start_date' to 'date_of_joining' and add 'role' column...")
        
        # Create new employees table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            department TEXT DEFAULT 'Tech',
            date_of_joining TEXT,
            role TEXT,
            joining_salary REAL,
            current_salary REAL,
            status TEXT DEFAULT 'Active',
            last_review_date TEXT,
            last_review_effective_date TEXT,
            resign_date TEXT,
            lwd TEXT
        );
        """)

        # Transfer data from employees to employees_new
        # Map start_date -> date_of_joining, role -> NULL initially
        cursor.execute("""
        INSERT INTO employees_new (id, name, department, date_of_joining, role, joining_salary, current_salary, status, last_review_date, last_review_effective_date, resign_date, lwd)
        SELECT id, name, department, start_date, NULL, joining_salary, current_salary, status, last_review_date, last_review_effective_date, resign_date, lwd FROM employees;
        """)

        # Drop old table
        cursor.execute("DROP TABLE employees;")

        # Rename employees_new to employees
        cursor.execute("ALTER TABLE employees_new RENAME TO employees;")
        
        conn.commit()
        print("Schema migration completed successfully!")
    else:
        print("Employees table already migrated or doesn't contain 'start_date'. Checking for 'role'...")
        if "role" not in cols:
            print("Adding 'role' column...")
            cursor.execute("ALTER TABLE employees ADD COLUMN role TEXT;")
            conn.commit()
            print("'role' column added successfully!")
        if "date_of_joining" not in cols and "start_date" not in cols:
            print("[WARNING] Unexpected schema. Table columns:", cols)

    # Re-enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 2. Load Excel sheet
    if not os.path.exists(EXCEL_PATH):
        print(f"[ERROR] Excel sheet not found at {EXCEL_PATH}. Updates cannot be applied.")
        conn.close()
        return

    print(f"Reading Excel updates from {EXCEL_PATH}...")
    df = pd.read_excel(EXCEL_PATH)
    
    # 3. Apply updates to the database
    cursor.execute("SELECT id, name, date_of_joining, role FROM employees")
    db_emps = cursor.fetchall()
    
    db_emp_dict = {name.strip().lower(): (eid, name, doj, rle) for eid, name, doj, rle in db_emps}
    
    updated_count = 0
    unmatched_excel = []
    
    for idx, row in df.iterrows():
        emp_name = str(row['Employee Name']).strip() if 'Employee Name' in row else None
        if not emp_name:
            continue
            
        excel_doj = parse_date(row.get('DOJ'))
        excel_role = str(row['Role']).strip() if 'Role' in row and pd.notna(row['Role']) else None
        
        key = emp_name.lower()
        if key in db_emp_dict:
            eid, name, current_doj, current_role = db_emp_dict[key]
            
            print(f"Updating employee {name} (ID: {eid}):")
            print(f"  DOJ:  {current_doj} -> {excel_doj}")
            print(f"  Role: {current_role} -> {excel_role}")
            
            cursor.execute("""
                UPDATE employees 
                SET date_of_joining = ?, role = ?
                WHERE id = ?
            """, (excel_doj, excel_role, eid))
            updated_count += 1
            
            # Remove from db_emp_dict to see who is missing
            db_emp_dict.pop(key)
        else:
            unmatched_excel.append((emp_name, excel_doj, excel_role))
            
    conn.commit()
    print(f"\nSuccessfully updated {updated_count} employees in the database!")
    
    if unmatched_excel:
        print("\n[WARNING] Excel rows that did not match any database employees:")
        for name, doj, role in unmatched_excel:
            print(f"  Name: {name} | DOJ: {doj} | Role: {role}")
            
    if db_emp_dict:
        print("\n[NOTE] Database employees that were NOT in the Excel sheet (their existing DOJs were preserved):")
        for key, (eid, name, doj, role) in db_emp_dict.items():
            print(f"  Name: {name} (ID: {eid}) | Preserved DOJ: {doj} | Role: {role}")
            
    conn.close()
    print("\nMigration and data import process complete!")

if __name__ == "__main__":
    migrate()
