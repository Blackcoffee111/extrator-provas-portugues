import json

meta_path = 'workspace/PT639_2024_F1/questoes_meta.json'
review_path = 'workspace/PT639_2024_F1/questoes_review.json'
output_path = 'workspace/PT639_2024_F1/questoes_raw.json'

with open(meta_path, 'r') as f:
    meta = json.load(f)

with open(review_path, 'r') as f:
    review = json.load(f)

def normalize_id(id_str):
    parts = id_str.split('-')
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[-1]}"
    return id_str

# Build map from meta: normalized_id -> item
meta_map = {normalize_id(m['id_item']): m for m in meta}

merged = []
for r in review:
    norm_id = normalize_id(r['id_item'])
    m = meta_map.get(norm_id, {})
    
    if not m:
        print(f"Warning: No meta found for normalized ID: {norm_id} (original: {r.get('id_item')})")
        # Try finding by numero_principal if meta_map fails
        # (Fall back logic here if needed, but normalized ID should work for Português)
    
    # Merge: review takes precedence for content, but keep meta's technical fields
    item = {**m, **r}
    
    # Ensure critical fields from meta are preserved
    if not item.get('source_span') and m.get('source_span'):
        item['source_span'] = m['source_span']
    if not item.get('texto_original') and m.get('texto_original'):
        item['texto_original'] = m['texto_original']
    if not item.get('id_item'): # Fallback to meta id if review's id is missing (unlikely)
        item['id_item'] = m.get('id_item', r.get('id_item'))
        
    merged.append(item)

with open(output_path, 'w') as f:
    json.dump(merged, f, indent=2, ensure_ascii=False)

print(f"Successfully merged {len(merged)} items to {output_path}")
