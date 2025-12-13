import re

# Read the template file
with open('templates/admin/manage_academics.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix all .lower() calls to handle potential null/integer values
replacements = [
    # Subject data attributes
    (r'data-name="{{ subject\[1\]\.lower\(\) }}"', 'data-name="{{ (subject[1]|string).lower() if subject[1] else \'\' }}"'),
    (r'data-course="{{ subject\[2\]\.lower\(\) }}"', 'data-course="{{ (subject[2]|string).lower() if subject[2] else \'\' }}"'),
    (r'data-class="{{ subject\[3\]\.lower\(\) }}"', 'data-class="{{ (subject[3]|string).lower() if subject[3] else \'\' }}"'),
    
    # Faculty allocation data attributes  
    (r'data-faculty="{{ alloc\[1\]\.lower\(\) }}"', 'data-faculty="{{ (alloc[1]|string).lower() if alloc[1] else \'\' }}"'),
    (r'data-subject="{{ alloc\[2\]\.lower\(\) }}"', 'data-subject="{{ (alloc[2]|string).lower() if alloc[2] else \'\' }}"'),
    (r'data-class="{{ alloc\[3\]\.lower\(\) }}"', 'data-class="{{ (alloc[3]|string).lower() if alloc[3] else \'\' }}"'),
    (r'data-division="{{ alloc\[4\]\.lower\(\) }}"', 'data-division="{{ (alloc[4]|string).lower() if alloc[4] else \'\' }}"'),
]

for pattern, replacement in replacements:
    content = re.sub(pattern, replacement, content)

# Write back the fixed content
with open('templates/admin/manage_academics.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed all .lower() calls in template to handle null/integer values safely")