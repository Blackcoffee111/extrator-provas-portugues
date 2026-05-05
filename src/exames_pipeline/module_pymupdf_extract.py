"""
Extração paralela com PyMuPDF — referência de texto nativo para o agente.

Roda em background junto com MinerU (não compete por CPU significativamente —
PyMuPDF puro lê camada de texto; MinerU faz OCR). Output: `prova_pymupdf.md`
no workspace, marcado por página, para o agente consultar durante a revisão
quando houver dúvida de OCR (diacríticos, sobrescritos, números fundidos).

Não substitui MinerU: imagens, tabelas e estrutura continuam vindo de lá.

CLI standalone:
    python -m exames_pipeline.module_pymupdf_extract <pdf> <workspace_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path


def extract_pymupdf_reference(pdf_path: Path, workspace_dir: Path) -> Path | None:
    """Extrai texto via PyMuPDF e grava em workspace_dir/prova_pymupdf.md.

    Devolve o caminho do ficheiro gerado, ou None se PyMuPDF não estiver disponível
    ou o PDF não tiver camada de texto.
    """
    try:
        import fitz  # type: ignore[import]
    except ImportError:
        print("[pymupdf] pymupdf não instalado — referência paralela não gerada.")
        return None

    if not pdf_path.exists():
        print(f"[pymupdf] ❌ PDF não encontrado: {pdf_path}")
        return None

    workspace_dir.mkdir(parents=True, exist_ok=True)
    out = workspace_dir / "prova_pymupdf.md"

    try:
        doc = fitz.open(str(pdf_path))
        with_text = sum(1 for p in doc if p.get_text("text").strip())
        total = len(doc)

        if with_text == 0:
            doc.close()
            print(f"[pymupdf] ⚠️  PDF sem camada de texto ({total} páginas) — referência não útil.")
            return None

        parts: list[str] = [
            f"<!-- Referência PyMuPDF — gerada em paralelo ao MinerU.\n"
            f"     Páginas com camada de texto: {with_text}/{total}.\n"
            f"     Use para verificar diacríticos, sobrescritos, ordinais quando o\n"
            f"     OCR do MinerU parecer suspeito. NÃO é o ficheiro a editar. -->\n"
        ]
        for i, page in enumerate(doc, start=1):
            parts.append(f"\n\n<!-- ==== PÁGINA {i} ==== -->\n")
            parts.append(page.get_text("text"))
        doc.close()

        out.write_text("".join(parts), encoding="utf-8")
        size_kb = out.stat().st_size / 1024
        print(f"[pymupdf] ✅ {out.name} ({size_kb:.1f} KB, {with_text}/{total} páginas com texto)")
        return out
    except Exception as exc:
        print(f"[pymupdf] ❌ erro: {exc}")
        return None


def main() -> int:
    if len(sys.argv) != 3:
        print("Uso: python -m exames_pipeline.module_pymupdf_extract <pdf> <workspace_dir>")
        return 1
    pdf_path = Path(sys.argv[1])
    ws_dir = Path(sys.argv[2])
    out = extract_pymupdf_reference(pdf_path, ws_dir)
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
