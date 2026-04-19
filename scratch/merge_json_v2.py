import json

meta_path = 'workspace/PT639_2024_F1/questoes_meta.json'
review_path = 'workspace/PT639_2024_F1/questoes_review.json'
output_path = 'workspace/PT639_2024_F1/questoes_raw.json'

with open(meta_path, 'r') as f:
    meta = json.load(f)

with open(review_path, 'r') as f:
    review = json.load(f)

# Build map from meta: (grupo, numero_principal) -> item
meta_map = {}
for m in meta:
    # Handle Group I parts (A, B, C) - just extract the first character of group
    group_letter = m.get('grupo', '')[0] if m.get('grupo') else ''
    key = (group_letter, m.get('numero_principal'))
    meta_map[key] = m

merged = []
for r in review:
    group_letter = r.get('grupo', '')[0] if r.get('grupo') else r.get('id_item', '')[0]
    num = r.get('numero_principal')
    
    key = (group_letter, num)
    m = meta_map.get(key, {})
    
    if not m:
        print(f"Warning: No meta found for {key} (id_item: {r.get('id_item')})")
    
    # Merge: review takes precedence for most fields, but keep meta's structural fields
    item = {**m, **r}
    
    # Ensure critical fields from meta are preserved if review has them as null/missing
    if not item.get('source_span') and m.get('source_span'):
        item['source_span'] = m['source_span']
    if not item.get('texto_original') and m.get('texto_original'):
        item['texto_original'] = m['texto_original']
        
    merged.append(item)

with open(output_path, 'w') as f:
    json.dump(merged, f, indent=2, ensure_ascii=False)

print(f"Successfully merged {len(merged)} items to {output_path}")
