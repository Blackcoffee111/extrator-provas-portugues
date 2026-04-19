import json
from pathlib import Path
import re

def merge_review_meta(workspace_dir: Path):
    review_path = workspace_dir / "questoes_review.json"
    meta_path = workspace_dir / "questoes_meta.json"
    raw_path = workspace_dir / "questoes_raw.json"

    if not review_path.exists():
        print(f"Error: {review_path} not found")
        return
    if not meta_path.exists():
        print(f"Error: {meta_path} not found")
        return

    review_list = json.loads(review_path.read_text(encoding="utf-8"))
    meta_list = json.loads(meta_path.read_text(encoding="utf-8"))

    meta_by_id = {m.get("id_item", ""): m for m in meta_list}
    max_ordem = max((m.get("ordem_item") or 0 for m in meta_list), default=0)
    ITEM_ID_RE = re.compile(r"^(?:[IVX]+-)?(?P<main>\d{1,3})(?:\.(?P<sub>\d{1,2}))?$")

    def _meta_fallback(id_, ordem):
        mat = ITEM_ID_RE.match(id_)
        main = int(mat.group("main")) if mat else 0
        sub = mat.group("sub") if mat else None
        return {
            "id_item": id_,
            "numero_questao": main,
            "ordem_item": ordem,
            "numero_principal": main,
            "subitem": sub,
            "materia": "Matemática A",
            "imagens_contexto": [],
            "pagina_origem": None,
            "fonte": "",
            "status": "draft",
            "texto_original": "",
            "source_span": None,
            "grupo_ids": [id_],
            "descricoes_imagens": {},
            "criterios_parciais": [],
            "resolucoes_alternativas": [],
        }

    merged = []
    for r in review_list:
        id_ = r.get("id_item", "")
        if id_ in meta_by_id:
            m = meta_by_id[id_]
        else:
            max_ordem += 1
            m = _meta_fallback(id_, max_ordem)
        merged.append({**m, **r})

    raw_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Successfully merged {len(merged)} items into {raw_path}")

if __name__ == "__main__":
    import sys
    workspace = Path("workspace/EX-MatA635-F2-2019")
    merge_review_meta(workspace)
