import json
import sys
import re

def fix_latex(text):
    if not isinstance(text, str): return text
    
    # Normalize special sequences (tabs/form feeds) back to LaTeX literals
    text = text.replace('\f', r'\frac')
    text = text.replace('\t', r'\to')
    
    # Regex that collapses any number of backslashes before a letter into a single backslash
    # Note: in Python raw strings, \\ means a literal \.
    # So r'\\+([a-zA-Z])' matches one or more backslashes followed by a letter.
    # The replacement r'\\\1' puts a single backslash followed by that letter.
    text = re.sub(r'\\+([a-zA-Z])', r'\\\1', text)
    
    return text

def process_file(path, item_id):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for item in data:
        # If item_id is provided, only fix that one. If None, fix ALL.
        if item_id is None or item.get('id_item') == item_id:
            item['solucao'] = fix_latex(item['solucao'])
            if 'criterios_parciais' in item:
                for cp in item['criterios_parciais']:
                    cp['descricao'] = fix_latex(cp['descricao'])

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    target_id = sys.argv[2] if len(sys.argv) > 2 else None
    process_file(sys.argv[1], target_id)
