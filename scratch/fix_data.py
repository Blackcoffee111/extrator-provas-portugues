import json
import re
from pathlib import Path

review_path = Path("workspace/EX-Port639-F1-2024_net/questoes_review.json")
meta_path = Path("workspace/EX-Port639-F1-2024_net/questoes_meta.json")

review = json.loads(review_path.read_text())

new_review = []
for item in review:
    # 1. Ignore I-ctx
    if item["id_item"] == "I-ctx":
        continue
    
    # 2. Fix numero_principal and numero_questao from id_item
    # Patterns: "I-1", "II-4", "III-1", "I-A-ctx"
    match = re.match(r"^(?:[IVX]+-)?(?:[A-C]-)?(?P<num>\d+|ctx)$", item["id_item"])
    if match:
        num_str = match.group("num")
        if num_str == "ctx":
            item["numero_principal"] = 0
            item["numero_questao"] = 0
        else:
            n = int(num_str)
            item["numero_principal"] = n
            item["numero_questao"] = n
    
    # Ensure items are reviewed
    item["reviewed"] = True
    new_review.append(item)

# Update review file (optional but keeps state clean)
review_path.write_text(json.dumps(new_review, indent=2, ensure_ascii=False))

# Now regenerate Meta from this clean Review list
new_meta = []
for i, rev_item in enumerate(new_review):
    meta_item = {
        "id_item": rev_item["id_item"],
        "numero_questao": rev_item["numero_questao"],
        "ordem_item": i + 1,
        "numero_principal": rev_item["numero_principal"],
        "subitem": rev_item.get("subitem"),
        "tipo_item": rev_item.get("tipo_item", "open_response"),
        "materia": "Português",
        "enunciado": rev_item.get("enunciado", ""),
        "alternativas": rev_item.get("alternativas", []),
        "tema": rev_item.get("tema", ""),
        "subtema": rev_item.get("subtema", ""),
        "tags": rev_item.get("tags", []),
        "imagens": rev_item.get("imagens", []),
        "imagens_contexto": [],
        "pagina_origem": None,
        "resposta_correta": rev_item.get("resposta_correta"),
        "fonte": "Exame Nacional, Português, 1.ª Fase, 2024",
        "status": "approved",
        "observacoes": rev_item.get("observacoes", []),
        "texto_original": rev_item.get("enunciado", ""),
        "source_span": {"line_start": 1, "line_end": 1},
        "enunciado_contexto_pai": rev_item.get("enunciado_contexto_pai", ""),
        "grupo_ids": [rev_item["id_item"]],
        "descricoes_imagens": {},
        "descricao_breve": rev_item.get("descricao_breve", "Item de exame 2024"),
        "solucao": "",
        "criterios_parciais": [],
        "resolucoes_alternativas": [],
        "grupo": rev_item.get("grupo", ""),
        "reviewed": True,
        "pool_opcional": rev_item.get("pool_opcional", ""),
        "palavras_min": rev_item.get("palavras_min"),
        "palavras_max": rev_item.get("palavras_max"),
        "linhas_referenciadas": rev_item.get("linhas_referenciadas", []),
        "parametros_classificacao": rev_item.get("parametros_classificacao", [])
    }
    new_meta.append(meta_item)

meta_path.write_text(json.dumps(new_meta, indent=2, ensure_ascii=False))
print(f"Data fixed: Removed I-ctx, fixed numbering for {len(new_meta)} items.")
