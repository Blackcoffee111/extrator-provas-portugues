"""
Teste de extração com PyMuPDF — alternativa ao MinerU.

Não toca no pipeline. Lê um PDF, extrai texto + imagens com fitz, e grava
o resultado num diretório paralelo (`workspace/<NOME>__pymupdf/`) sem
sobrescrever nada do MinerU.

Uso:
    python3.11 scratch/test_pymupdf_extract.py <pdf_path> [--out <dir>] [--mode <text|blocks|dict>]

Exemplos:
    # Extração simples
    python3.11 scratch/test_pymupdf_extract.py "provas fonte/.../EX_Port639_F1_2013_V1.pdf"

    # Comparar com workspace MinerU existente (lado a lado)
    python3.11 scratch/test_pymupdf_extract.py \\
        "provas fonte/.../EX_Port639_F1_2013_V1.pdf" \\
        --out workspace/EX-Port639-F1-2013_pymupdf

Modos:
    text   — get_text("text")  — texto plano, mais limpo (default)
    blocks — get_text("blocks") — preserva ordem por blocos (útil p/ multi-coluna)
    dict   — get_text("dict")   — estrutura completa (fontes, bbox, spans) — JSON

Após correr, comparar com o prova.md do MinerU:
    diff workspace/<MinerU>/prova.md workspace/<MinerU>__pymupdf/prova.md
    code -d workspace/<MinerU>/prova.md workspace/<MinerU>__pymupdf/prova.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERRO: pymupdf não instalado. pip install pymupdf", file=sys.stderr)
    sys.exit(1)


def extract_text_mode(doc: "fitz.Document", out_md: Path) -> None:
    lines: list[str] = []
    for i, page in enumerate(doc, start=1):
        lines.append(f"\n\n<!-- ==== PÁGINA {i} ==== -->\n")
        lines.append(page.get_text("text"))
    out_md.write_text("".join(lines), encoding="utf-8")
    print(f"[text]   {out_md} ({out_md.stat().st_size / 1024:.1f} KB)")


def extract_blocks_mode(doc: "fitz.Document", out_md: Path) -> None:
    lines: list[str] = []
    for i, page in enumerate(doc, start=1):
        lines.append(f"\n\n<!-- ==== PÁGINA {i} ==== -->\n")
        blocks = page.get_text("blocks")
        # blocks ordenados por (y, x) — leitura natural
        blocks.sort(key=lambda b: (round(b[1], 1), round(b[0], 1)))
        for b in blocks:
            x0, y0, x1, y1, text, block_no, block_type = b
            if block_type != 0:
                continue  # 0 = texto; 1 = imagem
            lines.append(text.rstrip() + "\n\n")
    out_md.write_text("".join(lines), encoding="utf-8")
    print(f"[blocks] {out_md} ({out_md.stat().st_size / 1024:.1f} KB)")


def extract_dict_mode(doc: "fitz.Document", out_json: Path) -> None:
    pages: list[dict] = []
    for i, page in enumerate(doc, start=1):
        pages.append({"page": i, "data": page.get_text("dict")})

    def _default(o):
        if isinstance(o, bytes):
            return f"<bytes len={len(o)}>"
        raise TypeError(f"não-serializável: {type(o).__name__}")

    out_json.write_text(
        json.dumps(pages, ensure_ascii=False, indent=2, default=_default),
        encoding="utf-8",
    )
    print(f"[dict]   {out_json} ({out_json.stat().st_size / 1024:.1f} KB)")


def extract_images(doc: "fitz.Document", img_dir: Path) -> int:
    img_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for page_num, page in enumerate(doc, start=1):
        for img_idx, img in enumerate(page.get_images(full=True), start=1):
            xref = img[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4:  # CMYK → RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                out = img_dir / f"page{page_num:03d}_img{img_idx:02d}.png"
                pix.save(str(out))
                pix = None
                n += 1
            except Exception as exc:
                print(f"  ! falha imagem p{page_num} #{img_idx}: {exc}")
    return n


def detect_text_layer(doc: "fitz.Document") -> tuple[int, int]:
    """Retorna (páginas com texto, total)."""
    with_text = sum(1 for p in doc if p.get_text("text").strip())
    return with_text, len(doc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf_path", type=Path)
    ap.add_argument("--out", type=Path, default=None,
                    help="Diretório de saída. Default: workspace/<stem>__pymupdf")
    ap.add_argument("--mode", choices=["text", "blocks", "dict", "all"], default="all",
                    help="Modo de extração (default: all — gera os 3).")
    ap.add_argument("--no-images", action="store_true", help="Não extrair imagens.")
    args = ap.parse_args()

    if not args.pdf_path.exists():
        print(f"ERRO: PDF não encontrado: {args.pdf_path}", file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parent.parent
    out_dir = args.out or (repo_root / "workspace" / f"{args.pdf_path.stem}__pymupdf")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"PDF:    {args.pdf_path}")
    print(f"Saída:  {out_dir}")

    doc = fitz.open(str(args.pdf_path))
    with_text, total = detect_text_layer(doc)
    print(f"Páginas com camada de texto: {with_text}/{total}")
    if with_text == 0:
        print("⚠️  PDF parece ser 100% imagem (escaneado). PyMuPDF puro não fará OCR — "
              "use MinerU ou rode OCR antes (ocrmypdf).")

    if args.mode in ("text", "all"):
        extract_text_mode(doc, out_dir / "prova.md")
    if args.mode in ("blocks", "all"):
        extract_blocks_mode(doc, out_dir / "prova_blocks.md")
    if args.mode in ("dict", "all"):
        extract_dict_mode(doc, out_dir / "prova_dict.json")

    if not args.no_images:
        n = extract_images(doc, out_dir / "images")
        print(f"Imagens extraídas: {n}")

    doc.close()
    print("\nPróximo passo — comparar com MinerU:")
    print(f"  diff workspace/<MinerU>/prova.md {out_dir}/prova.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
