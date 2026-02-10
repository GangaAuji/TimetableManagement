import re
import os
import mysql.connector
from config import Config

# Get all permissions used in code
code_perms = set()
routes_dir = 'routes'

# Track routes without any protection
unprotected_routes = []
# Track routes with role-only protection (might need granular perms)
role_only_routes = []

# Protection decorators to look for
protection_patterns = [
    '@has_permission',
    '@admin_required', 
    '@teacher_required',
    '@student_required',
    '@login_required'
]

for root, dirs, files in os.walk(routes_dir):
    for file in files:
        if file.endswith('.py') and not file.startswith('__'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                matches = re.findall(r"@has_permission\(['\"]([^'\"]+)['\"]", content)
                code_perms.update(matches)
                
                # Find routes and check their protection
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    # Look for route decorators
                    if re.match(r'\s*@\w+(_bp)?\.route\(', line):
                        # Check decorators between route and def
                        has_permission = False
                        has_role_check = False
                        func_name = None
                        
                        for j in range(i, min(i+10, len(lines))):
                            check_line = lines[j]
                            if '@has_permission' in check_line:
                                has_permission = True
                            if any(p in check_line for p in ['@admin_required', '@teacher_required', '@student_required', '@login_required']):
                                has_role_check = True
                            if check_line.strip().startswith('def '):
                                func_match = re.search(r'def (\w+)\(', check_line)
                                if func_match:
                                    func_name = func_match.group(1)
                                break
                        
                        if func_name:
                            rel_path = os.path.relpath(filepath, '.')
                            # Skip auth routes (login, logout, register, home)
                            if 'auth_routes' in filepath and func_name in ['login', 'logout', 'register', 'home', 'admin_login']:
                                continue
                            
                            if not has_permission and not has_role_check:
                                unprotected_routes.append((rel_path, func_name, i+1))
                            elif has_role_check and not has_permission:
                                role_only_routes.append((rel_path, func_name, i+1))

# Get all permissions from DB
conn = mysql.connector.connect(
    host=Config.MYSQL_HOST,
    user=Config.MYSQL_USER,
    password=Config.MYSQL_PASSWORD,
    database=Config.MYSQL_DB
)
cursor = conn.cursor()
cursor.execute('SELECT name FROM permissions')
db_perms = set(r[0] for r in cursor.fetchall())
conn.close()

# Find mismatches
missing_in_db = code_perms - db_perms

print('=' * 70)
print('PERMISSIONS AUDIT REPORT')
print('=' * 70)

print('\n=== ⛔ UNPROTECTED ROUTES (NO DECORATOR AT ALL) ===')
if unprotected_routes:
    for filepath, func, line in unprotected_routes:
        print(f'  ❌ {filepath}:{line} - {func}()')
else:
    print('  ✅ All routes have some protection!')

print('\n=== ⚠️  ROLE-ONLY ROUTES (no granular @has_permission) ===')
if role_only_routes:
    for filepath, func, line in role_only_routes:
        print(f'  📌 {filepath}:{line} - {func}()')
else:
    print('  ✅ All admin routes use granular permissions!')

print('\n=== MISSING PERMISSIONS IN DATABASE ===')
if missing_in_db:
    for p in sorted(missing_in_db):
        print(f'  ❌ {p}')
else:
    print('  ✅ All permissions exist in database!')

print('\n' + '=' * 70)
print(f'Permissions in code:  {len(code_perms)}')
print(f'Permissions in DB:    {len(db_perms)}')
print(f'Unprotected routes:   {len(unprotected_routes)}')
print(f'Role-only routes:     {len(role_only_routes)}')
print('=' * 70)
