import re

# Read the academic_routes.py file
with open('routes/academic_routes.py', 'r') as f:
    content = f.read()

# Replace all year_name references with name in SQL queries
# This is safer than a global replace since it targets SQL contexts
replacements = [
    ('year_name', 'name'),  # In column names
    ('ay.year_name', 'ay.name'),  # In aliased column references
    ("INSERT INTO academic_years (year_name,", "INSERT INTO academic_years (name,"),
    ("SET year_name =", "SET name ="),
]

for old, new in replacements:
    content = content.replace(old, new)

# Write back the corrected content
with open('routes/academic_routes.py', 'w') as f:
    f.write(content)

print("Fixed all year_name references in academic_routes.py")

# Now fix the admin_routes.py classes API
with open('routes/admin_routes.py', 'r') as f:
    admin_content = f.read()

# Fix the classes API to just return all classes since they don't have course_id
admin_content = admin_content.replace(
    'cursor.execute("SELECT id, name FROM classes WHERE course_id = %s", [cid])',
    'cursor.execute("SELECT id, name FROM classes")'
)

with open('routes/admin_routes.py', 'w') as f:
    f.write(admin_content)

print("Fixed classes API in admin_routes.py")