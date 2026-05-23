import json
import glob
import os

target_doctypes = [
    'custody_article.json',
    'custody_issue.json',
    'custody_return.json',
    'custody_damage_assessment.json',
    'non_financial_depreciation_snapshot.json',
    'facility_asset.json',
    'facility_asset_movement.json',
    'facility_asset_custody_assignment.json'
]

files = glob.glob('apex_habitat/habitat/doctype/*/*.json')
modified_count = 0

roles_to_add = [
    {
        "role": "Accommodation Manager",
        "read": 1, "write": 1, "create": 1, "delete": 1, "submit": 1, "cancel": 1, "amend": 1
    },
    {
        "role": "Resident Supervisor",
        "read": 1, "write": 1, "create": 1
    }
]

for file in files:
    filename = os.path.basename(file)
    if filename in target_doctypes:
        with open(file, 'r') as f:
            data = json.load(f)
            
        permissions = data.get('permissions', [])
        existing_roles = {p.get('role') for p in permissions}
        
        modified = False
        for role_perm in roles_to_add:
            if role_perm['role'] not in existing_roles:
                new_perm = role_perm.copy()
                new_perm['doctype'] = 'DocPerm'
                
                # Check if doctype is submittable
                if data.get('is_submittable') != 1:
                    new_perm.pop('submit', None)
                    new_perm.pop('cancel', None)
                    new_perm.pop('amend', None)
                
                permissions.append(new_perm)
                modified = True
        
        if modified:
            # Fix indexes
            for i, p in enumerate(permissions):
                p['idx'] = i + 1
            data['permissions'] = permissions
            
            with open(file, 'w') as f:
                json.dump(data, f, indent=1, ensure_ascii=False)
                f.write('\n')
            modified_count += 1
            print(f"Updated permissions for: {data.get('name')}")

print(f"Total files updated with permissions: {modified_count}")
