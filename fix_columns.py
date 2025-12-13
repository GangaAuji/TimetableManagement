import re

# Read the academic_routes.py file
with open('routes/academic_routes.py', 'r') as f:
    content = f.read()

# Fix the main query in manage_academics that's causing the error
old_query = """        SELECT s.id, s.name, s.course_code, s.course_type, s.theory_practical,
               s.credits, s.theory_credits, s.practical_credits,
               s.lectures_per_week, s.is_elective, s.is_mandatory,
               c.name as course_name, c.program,
               d.name as department_name, 
               sem.semester_name,
               ay.name as academic_year_name"""

new_query = """        SELECT s.id, s.name, s.course_code, s.course_type, s.theory_practical,
               s.credits, s.theory_credits, s.practical_credits,
               s.lectures_per_week, s.is_elective,
               c.name as course_name, c.program,
               d.name as department_name, 
               sem.semester_name,
               ay.name as academic_year_name"""

content = content.replace(old_query, new_query)

# Remove is_mandatory from all INSERT and UPDATE statements for subjects
content = re.sub(r',\s*is_mandatory,', ',', content)
content = re.sub(r',\s*is_mandatory\s*\)', ')', content)
content = re.sub(r'\s*is_mandatory\s*=\s*%s,', '', content)
content = re.sub(r',\s*is_mandatory\s*=\s*%s', '', content)

# Remove is_mandatory variable assignments (but keep the ones for elective_groups)
lines = content.split('\n')
fixed_lines = []
for line in lines:
    # Skip is_mandatory assignments in subject functions but keep in elective functions
    if 'is_mandatory = ' in line and ('add_subject' in content[max(0, content[:content.find(line)].rfind('def')):content.find(line)] or 
                                       'edit_subject' in content[max(0, content[:content.find(line)].rfind('def')):content.find(line)]):
        continue
    fixed_lines.append(line)

content = '\n'.join(fixed_lines)

# Fix the subject data parsing in API endpoints
content = re.sub(
    r"'is_mandatory': bool\(subject\[14\]\) if len\(subject\) > 14 else False,",
    "# 'is_mandatory' column removed",
    content
)

# Write back the corrected content
with open('routes/academic_routes.py', 'w') as f:
    f.write(content)

print("Fixed all column reference issues in academic_routes.py")