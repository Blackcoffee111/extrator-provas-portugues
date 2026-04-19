import json
from pathlib import Path

ws_dir = Path('workspace/EX-Port639-F1-2024')
p = ws_dir / 'questoes_review.json'
q_list = json.loads(p.read_text(encoding='utf-8'))

for i, q in enumerate(q_list):
    q['source_span'] = {'line_start': 0, 'line_end': 0}
    q['texto_original'] = q['enunciado']
    q['ordem_item'] = i + 1
    q['materia'] = 'Português'
    q['disciplina'] = 'Português'
    q['fonte'] = 'Exame Nacional, Português, 1.ª Fase, 2024'
    q['reviewed'] = True

p.write_text(json.dumps(q_list, indent=2, ensure_ascii=False), encoding='utf-8')

raw_p = ws_dir / 'questoes_raw.json'
raw_p.write_text(json.dumps(q_list, indent=2, ensure_ascii=False), encoding='utf-8')
print(f"Fixed {len(q_list)} items.")
