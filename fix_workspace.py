import json

file_path = 'apex_habitat/habitat/workspace/setup/setup.json'
with open(file_path, 'r') as f:
    data = json.load(f)

content = json.loads(data['content'])
new_shortcuts = [
    {"id": "short_bldg", "type": "shortcut", "data": {"shortcut_name": "Accommodation Building", "col": 3}},
    {"id": "short_room", "type": "shortcut", "data": {"shortcut_name": "Accommodation Room", "col": 3}},
    {"id": "short_mat", "type": "shortcut", "data": {"shortcut_name": "Maintenance Material", "col": 3}},
    {"id": "short_tpl", "type": "shortcut", "data": {"shortcut_name": "Maintenance Material Template", "col": 3}}
]

# Find the index of the existing shortcut
insert_idx = -1
for i, block in enumerate(content):
    if block.get('type') == 'shortcut':
        insert_idx = i
        break

if insert_idx != -1:
    for shortcut in reversed(new_shortcuts):
        content.insert(insert_idx + 1, shortcut)

data['content'] = json.dumps(content)

with open(file_path, 'w') as f:
    json.dump(data, f, indent=1, ensure_ascii=False)
    f.write('\n')

print("Workspace layout fixed.")
