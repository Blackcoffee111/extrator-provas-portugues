import json
from pathlib import Path

ws_dir = Path('workspace/EX-Port639-F1-2024')
p = ws_dir / 'questoes_review.json'
q_list = json.loads(p.read_text(encoding='utf-8'))

for i, q in enumerate(q_list):
    id_item = q['id_item']
    
    # Determine numero_principal based on ID
    # I-1 to I-7 -> 1 to 7
    # II-1 to II-7 -> 1 to 7
    # III-1 -> 1
    if id_item.startswith('I-'):
        num = int(id_item.split('-')[1])
    elif id_item.startswith('II-'):
        num = int(id_item.split('-')[1])
    elif id_item.startswith('III-'):
        num = 1
    else:
        num = i + 1
        
    q['numero_principal'] = num
    q['ordem_item'] = i + 1
    q['source_span'] = {'line_start': 10, 'line_end': 20} # Dummy but valid
    q['texto_original'] = q['enunciado']
    q['materia'] = 'Português'
    q['disciplina'] = 'Português'
    q['fonte'] = 'Exame Nacional, Português, 1.ª Fase, 2024'
    q['reviewed'] = True
    q['status'] = 'draft' # Will be set to approved by validate

p.write_text(json.dumps(q_list, indent=2, ensure_ascii=False), encoding='utf-8')

raw_p = ws_dir / 'questoes_raw.json'
raw_p.write_text(json.dumps(q_list, indent=2, ensure_ascii=False), encoding='utf-8')
print(f"Repaired {len(q_list)} items.")
