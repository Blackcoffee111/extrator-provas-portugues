"""
Teste 1-A: recortar imagens do PDF original usando bboxes do MinerU
e comparar lado a lado com as imagens pré-processadas atuais.

Uso:
  python3.11 scratch/test_reextract_images.py <workspace_name> <pdf_path>

Exemplos:
  python3.11 scratch/test_reextract_images.py EX-Port639-F2-2023_net "provas fonte/.../F2-2023-V1.pdf"
  python3.11 scratch/test_reextract_images.py EX-Port639-EE-2024_net "provas fonte/.../EE-2024-V1.pdf"

Sem escritas destrutivas — saída em scratch/reextract_test_output/<workspace>/.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path("/Users/adrianoushinohama/dev/Exames Nacionais/Provas de portugues")
WORKTREE = ROOT / ".claude/worktrees/strange-feynman-2864c8"

DPI = 220
PADDING_PT = 4.0

if len(sys.argv) != 3:
    print(__doc__)
    sys.exit(1)

WORKSPACE_NAME = sys.argv[1]
ORIGINAL_PDF = Path(sys.argv[2])
if not ORIGINAL_PDF.is_absolute():
    ORIGINAL_PDF = WORKTREE / ORIGINAL_PDF

WORKSPACE = ROOT / "workspace" / WORKSPACE_NAME
MIDDLE_JSON = WORKSPACE / "preprocessed_input/ocr/preprocessed_input_middle.json"
CONTENT_LIST = WORKSPACE / "preprocessed_input/ocr/preprocessed_input_content_list.json"
CURRENT_IMGS = WORKSPACE / "imagens_extraidas"

OUT_DIR = WORKTREE / "scratch/reextract_test_output" / WORKSPACE_NAME


def extract_blocks_from_middle() -> list[dict]:
    """Lê middle.json e devolve lista de {page_idx, bbox_pt, type, img_path}."""
    data = json.loads(MIDDLE_JSON.read_text())
    content_list = json.loads(CONTENT_LIST.read_text())

    # Mapeia (page_idx, type) → img_path via content_list (ordem preservada)
    img_map: dict[tuple[int, str], list[str]] = {}
    for entry in content_list:
        t = entry.get("type")
        if t in ("image", "table"):
            key = (entry["page_idx"], t)
            img_map.setdefault(key, []).append(entry["img_path"])

    blocks: list[dict] = []
    for page in data["pdf_info"]:
        page_idx = page["page_idx"]
        page_size = page["page_size"]  # [w, h] em pt
        counters: dict[str, int] = {"image": 0, "table": 0}
        for block in page.get("para_blocks", []):
            t = block.get("type")
            if t not in ("image", "table"):
                continue
            img_paths = img_map.get((page_idx, t), [])
            idx = counters[t]
            counters[t] += 1
            if idx >= len(img_paths):
                print(f"  ⚠️  sem img_path para {t} #{idx} na pág {page_idx}")
                continue
            blocks.append({
                "page_idx": page_idx,
                "type": t,
                "bbox_pt": block["bbox"],  # coords em pt do PDF
                "page_size": page_size,
                "img_name": Path(img_paths[idx]).name,
            })
    return blocks


def crop_from_pdf(pdf_path: Path, page_idx: int, bbox: list[float], out_path: Path, dpi: int = DPI, padding: float = PADDING_PT) -> tuple[int, int]:
    doc = fitz.open(str(pdf_path))
    page = doc[page_idx]
    x0, y0, x1, y1 = bbox
    clip = fitz.Rect(
        max(0, x0 - padding),
        max(0, y0 - padding),
        min(page.rect.width, x1 + padding),
        min(page.rect.height, y1 + padding),
    )
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pix = page.get_pixmap(clip=clip, matrix=matrix, alpha=False)
    pix.save(str(out_path))
    dims = (pix.width, pix.height)
    doc.close()
    return dims


def main():
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    (OUT_DIR / "current_preprocessed").mkdir()
    (OUT_DIR / "reextracted_original").mkdir()

    blocks = extract_blocks_from_middle()
    print(f"Blocos encontrados: {len(blocks)}")

    rows = []
    for b in blocks:
        name = b["img_name"]
        # copia a imagem atual (pré-processada)
        src_current = CURRENT_IMGS / name
        dst_current = OUT_DIR / "current_preprocessed" / name
        if src_current.exists():
            shutil.copy2(src_current, dst_current)
            cur_size_kb = dst_current.stat().st_size / 1024
        else:
            cur_size_kb = None
            print(f"  ⚠️  imagem atual ausente: {name}")

        # recorta do PDF original
        dst_reex = OUT_DIR / "reextracted_original" / name
        dims = crop_from_pdf(ORIGINAL_PDF, b["page_idx"], b["bbox_pt"], dst_reex)
        reex_size_kb = dst_reex.stat().st_size / 1024

        rows.append({
            "name": name,
            "type": b["type"],
            "page": b["page_idx"] + 1,
            "bbox_pt": b["bbox_pt"],
            "reex_dims": dims,
            "cur_size_kb": cur_size_kb,
            "reex_size_kb": reex_size_kb,
        })
        print(f"  {b['type']:5s} pág {b['page_idx']+1}  bbox={b['bbox_pt']}  → {name}  ({dims[0]}x{dims[1]}, {reex_size_kb:.1f} KB)")

    # Gera HTML de comparação lado a lado
    html = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>Comparação de imagens</title>",
        "<style>",
        "body{font-family:-apple-system,sans-serif;margin:20px;background:#fafafa}",
        "table{border-collapse:collapse;width:100%;background:#fff}",
        "th,td{border:1px solid #ddd;padding:12px;vertical-align:top;text-align:left}",
        "th{background:#f0f0f0}",
        "img{max-width:100%;height:auto;border:1px solid #ccc;display:block}",
        ".meta{font-size:12px;color:#666;margin-top:6px}",
        "h1{color:#333}",
        "</style></head><body>",
        f"<h1>Comparação — {WORKSPACE.name}</h1>",
        f"<p><b>PDF original:</b> <code>{ORIGINAL_PDF.name}</code><br>",
        f"<b>Parâmetros do recorte:</b> DPI={DPI}, padding={PADDING_PT}pt</p>",
        "<table><thead><tr>",
        "<th>Metadata</th>",
        "<th>Atual (pré-processada)</th>",
        "<th>Re-extraída do original</th>",
        "</tr></thead><tbody>",
    ]
    for r in rows:
        meta = (
            f"<b>{r['type']}</b> — pág {r['page']}<br>"
            f"<code>{r['name'][:16]}…</code><br>"
            f"<div class='meta'>bbox_pt={r['bbox_pt']}<br>"
            f"recortada: {r['reex_dims'][0]}×{r['reex_dims'][1]}px<br>"
            f"atual: {r['cur_size_kb']:.1f} KB · nova: {r['reex_size_kb']:.1f} KB</div>"
        )
        html.append("<tr>")
        html.append(f"<td>{meta}</td>")
        html.append(f"<td><img src='current_preprocessed/{r['name']}'></td>")
        html.append(f"<td><img src='reextracted_original/{r['name']}'></td>")
        html.append("</tr>")
    html.append("</tbody></table></body></html>")

    (OUT_DIR / "index.html").write_text("\n".join(html))
    print(f"\n✅ Pronto. Abre: {OUT_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
