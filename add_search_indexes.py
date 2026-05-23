import json
import glob

files = glob.glob('apex_habitat/habitat/doctype/*/*.json')
modified_count = 0

target_fields = ['employee', 'building', 'room', 'bed', 'site']

for file in files:
    with open(file, 'r') as f:
        data = json.load(f)
        
    modified = False
    for field in data.get('fields', []):
        if field.get('fieldname') in target_fields and field.get('fieldtype') == 'Link':
            if field.get('search_index') != 1:
                field['search_index'] = 1
                modified = True
                
    if modified:
        with open(file, 'w') as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.write('\n')
        modified_count += 1
        print(f"Added indexes to: {data.get('name')}")

print(f"Total files updated with search indexes: {modified_count}")
