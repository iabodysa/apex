import json

def fix_room():
    with open('apex_habitat/habitat/doctype/accommodation_room/accommodation_room.json', 'r') as f:
        data = json.load(f)
    data['autoname'] = 'field:room_number'
    if 'naming_rule' in data:
        del data['naming_rule']
    with open('apex_habitat/habitat/doctype/accommodation_room/accommodation_room.json', 'w') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write('\n')

def fix_bed():
    with open('apex_habitat/habitat/doctype/accommodation_bed/accommodation_bed.json', 'r') as f:
        data = json.load(f)
    data['autoname'] = 'field:bed_code'
    if 'naming_rule' in data:
        del data['naming_rule']
    with open('apex_habitat/habitat/doctype/accommodation_bed/accommodation_bed.json', 'w') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write('\n')

fix_room()
fix_bed()
print("Fixed autoname in JSON files!")
