"""Triagem de páginas — selecciona o intervalo útil de um PDF antes da extracção pesada.

Para CCs do IAVE, a maior parte das páginas iniciais é genérica ("Critérios Gerais").
Para provas (V1), a primeira página é tipicamente instruções. Esta triagem identifica
o intervalo útil via heurística textual rápida (PyMuPDF) e gera um contact sheet
(grid de thumbnails) para o agente verificar visualmente numa única chamada.

Output: `triage/pages_manifest.json` + `triage/contact_sheet.png` no workspace.

CLI:
    python -m exames_pipeline.module_triage <pdf> [--workspace NAME] [--kind auto|cc|prova]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# ── Âncoras textuais ─────────────────────────────────────────────────────────

# CC: cabeçalho da secção de critérios específicos. Tem que estar seguido de "GRUPO"
# para não bater em referências cruzadas dentro do texto dos Critérios Gerais.
_CC_SECTION_RE = re.compile(
    r"crit[eé]rios?\s+espec[ií]ficos\s+de\s+classifica[cç][aã]o"
    r"[\s\S]{0,300}?"  # tolera linhas extras tipo "E RESPECTIVOS CENÁRIOS DE RESPOSTA" (2007)
    r"GRUPO\s+I",
    re.IGNORECASE,
)

# CC: marcadores de páginas descartáveis (conteúdo genérico repetido em todas as provas).
# Usados como fallback quando a âncora de início não está presente (provas pré-2018).
_CC_DISCARDABLE_MARKERS = [
    "CRITÉRIOS GERAIS DE CLASSIFICAÇÃO",
    "CRITERIOS GERAIS DE CLASSIFICACAO",
    "Factores de desvalorização",
    "Fatores de desvalorização",
]

# Prova: a primeira página com "GRUPO I" é o início real do enunciado.
_PROVA_START_ANCHORS = [
    "GRUPO I",
]

# Marcadores que confirmam que uma página tem conteúdo útil (não é só lixo).
_GROUP_RE = re.compile(r"\bGRUPO\s+(?:I|II|III|IV)\b")
_COTACOES_RE = re.compile(r"\bCOTAÇÕES\b|\bCotações\b")


# ── Resultado ────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class TriageResult:
    pdf_path: Path
    kind: str                              # "cc" | "prova"
    total_pages: int
    pages_to_process: list[int]            # 1-indexed
    pages_excluded: dict[int, str]         # 1-indexed → motivo
    method: str                            # "textual_heuristic" | "fallback_keep_all"
    confidence: str                        # "high" | "medium" | "low"
    needs_review: bool
    notes: list[str] = field(default_factory=list)
    contact_sheet_path: Path | None = None
    manifest_path: Path | None = None

    def to_dict(self) -> dict:
        return {
            "pdf_path": str(self.pdf_path),
            "kind": self.kind,
            "total_pages": self.total_pages,
            "pages_to_process": self.pages_to_process,
            "pages_excluded": {str(k): v for k, v in sorted(self.pages_excluded.items())},
            "method": self.method,
            "confidence": self.confidence,
            "needs_review": self.needs_review,
            "notes": self.notes,
            "contact_sheet": self.contact_sheet_path.name if self.contact_sheet_path else None,
        }


# ── Detecção de tipo ─────────────────────────────────────────────────────────

_CC_NAME_PATTERNS = [
    re.compile(r"(?:^|[-_])CC(?:[-_]|\.|$)"),    # EX-...-CC_net, ...-CC-VD-...
    re.compile(r"(?:^|[-_])CC[FP]\d"),            # portuguesB639_ccf1_07, _ccp1_
    re.compile(r"CRITERIOS?"),                    # Portugues639_criterios_..., CRITERIO_...
    re.compile(r"CC[-_]?VD"),                     # CC-VD, CCVD
]


def detect_kind(pdf_path: Path) -> str:
    """Heurística pelo nome do ficheiro. Vários padrões cobrem nomenclaturas
    diferentes do IAVE ao longo dos anos (2006: ccf1; 2010: criterios; 2024: CC-VD)."""
    name = pdf_path.name.upper()
    if any(p.search(name) for p in _CC_NAME_PATTERNS):
        return "cc"
    return "prova"


# ── Heurística textual ───────────────────────────────────────────────────────

def _find_first_page_with(doc, anchors: Iterable[str]) -> int | None:
    """Devolve o índice 1-indexed da primeira página com qualquer das âncoras (case-insensitive)."""
    needles = [a.casefold() for a in anchors]
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").casefold()
        if any(a in text for a in needles):
            return i
    return None


def _find_first_page_re(doc, regex: re.Pattern[str]) -> int | None:
    """Primeira página onde o regex casa."""
    for i, page in enumerate(doc, start=1):
        if regex.search(page.get_text("text")):
            return i
    return None


def _page_contains_any(page, anchors: Iterable[str]) -> bool:
    text = page.get_text("text").casefold()
    return any(a.casefold() in text for a in anchors)


def _last_useful_page(doc) -> int:
    """Última página com texto não-trivial. Páginas em branco no fim são cortadas."""
    last = len(doc)
    while last > 0:
        text = doc[last - 1].get_text("text").strip()
        if len(text) >= 100:
            return last
        last -= 1
    return len(doc)


def triage_textual(pdf_path: Path, kind: str) -> TriageResult:
    import fitz  # noqa: PLC0415

    doc = fitz.open(str(pdf_path))
    total = len(doc)
    excluded: dict[int, str] = {}
    notes: list[str] = []

    if kind == "cc":
        start = _find_first_page_re(doc, _CC_SECTION_RE)
        if start is not None:
            for p in range(1, start):
                excluded[p] = "Critérios Gerais (genérico, descartável)"
        else:
            # Fallback: procurar a última página que contém marcadores descartáveis;
            # tudo até essa (inclusive) sai. Capa (p1) também sai por convenção.
            last_discardable = 0
            for i, page in enumerate(doc, start=1):
                if _page_contains_any(page, _CC_DISCARDABLE_MARKERS):
                    last_discardable = max(last_discardable, i)
            if last_discardable > 0:
                excluded[1] = "capa / cabeçalho IAVE"
                for p in range(2, last_discardable + 1):
                    excluded[p] = "Critérios Gerais (genérico, descartável)"
                notes.append(
                    "âncora primária não encontrada — usado fallback por marcadores descartáveis"
                )
            else:
                doc.close()
                notes.append("nenhuma âncora CC encontrada — manter todas as páginas")
                return TriageResult(
                    pdf_path=pdf_path, kind=kind, total_pages=total,
                    pages_to_process=list(range(1, total + 1)),
                    pages_excluded={}, method="fallback_keep_all",
                    confidence="low", needs_review=True, notes=notes,
                )
    elif kind == "prova":
        start = _find_first_page_with(doc, _PROVA_START_ANCHORS)
        if start is None:
            start = 1
            notes.append("âncora 'GRUPO I' não encontrada — manter todas as páginas")
        else:
            for p in range(1, start):
                excluded[p] = "instruções iniciais / cabeçalho"
    else:
        doc.close()
        raise ValueError(f"kind desconhecido: {kind!r}")

    end = _last_useful_page(doc)
    for p in range(end + 1, total + 1):
        excluded[p] = "página em branco no fim"

    pages_to_process = [p for p in range(1, total + 1) if p not in excluded]

    used_fallback = any("fallback" in n for n in notes)
    if used_fallback:
        confidence = "medium"
    else:
        confidence = "high"
    if len(pages_to_process) < 2:
        confidence = "low"
        notes.append(f"apenas {len(pages_to_process)} páginas mantidas — verificar manualmente")
    elif kind == "cc" and len(excluded) < 2:
        # CCs do IAVE costumam ter 3+ páginas iniciais descartáveis. Menos que isso é suspeito.
        confidence = "medium"
        notes.append("menos páginas descartadas que o esperado para um CC — verificar")

    doc.close()
    return TriageResult(
        pdf_path=pdf_path, kind=kind, total_pages=total,
        pages_to_process=pages_to_process,
        pages_excluded=excluded,
        method="textual_heuristic",
        confidence=confidence,
        needs_review=(confidence != "high"),
        notes=notes,
    )


# ── Contact sheet ────────────────────────────────────────────────────────────

def render_contact_sheet(
    pdf_path: Path,
    out_path: Path,
    excluded: dict[int, str],
    *,
    dpi: int = 80,
    cols: int | None = None,
    label_height: int = 22,
) -> Path:
    """Gera grid de thumbnails. Páginas excluídas ficam com banda vermelha."""
    import fitz  # noqa: PLC0415
    from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415

    doc = fitz.open(str(pdf_path))
    n = len(doc)
    if cols is None:
        cols = min(6, max(3, int(math.ceil(math.sqrt(n)))))
    rows = math.ceil(n / cols)

    thumbs: list[Image.Image] = []
    for i, page in enumerate(doc, start=1):
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        thumbs.append(img)
    doc.close()

    cell_w = max(t.width for t in thumbs)
    cell_h = max(t.height for t in thumbs) + label_height
    sheet_w = cell_w * cols + (cols + 1) * 4
    sheet_h = cell_h * rows + (rows + 1) * 4

    sheet = Image.new("RGB", (sheet_w, sheet_h), (240, 240, 240))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except OSError:
        font = ImageFont.load_default()

    for idx, thumb in enumerate(thumbs):
        page_num = idx + 1
        col = idx % cols
        row = idx // cols
        x = 4 + col * (cell_w + 4)
        y = 4 + row * (cell_h + 4)
        is_excluded = page_num in excluded
        bg = (255, 220, 220) if is_excluded else (220, 255, 220)
        draw.rectangle([x - 2, y - 2, x + cell_w + 2, y + cell_h + 2], fill=bg)
        # centra a thumbnail na célula
        tx = x + (cell_w - thumb.width) // 2
        ty = y + label_height + (cell_h - label_height - thumb.height) // 2
        sheet.paste(thumb, (tx, ty))
        # rótulo
        status = "✗" if is_excluded else "✓"
        label = f"p{page_num} {status}"
        draw.text((x + 6, y + 4), label, fill=(0, 0, 0), font=font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, format="PNG", optimize=True)
    return out_path


# ── Preparação de páginas para extracção visual ──────────────────────────────


# Marcadores de margem nos excertos PT (números 1-3 dígitos).
_MARGIN_NUM_RE = re.compile(r"^\d{1,3}$")
# Largura máxima (em points PDF, 72/inch) de uma linha que é apenas marcador
# de margem. "5" tem ~6pt; "10"/"15" têm ~12pt; "100" teria ~18pt. 30pt cobre
# largo, com folga, sem apanhar texto curto inline.
_MARGIN_LINE_MAX_WIDTH = 30.0


def _extract_text_with_inline_margin_numbers(page) -> str:
    """Extrai texto PyMuPDF preservando marcadores de margem in-line.

    O método default `page.get_text("text")` lê páginas em ordem de coluna —
    os números de margem dos excertos PT (5, 10, 15, …) saem todos juntos
    num bloco no topo da página, separados das suas linhas de corpo. Isto
    confunde o sub-agente Sonnet que tem de inserir esses marcadores no
    prova.md, frequentemente colocando-os na linha errada.

    Esta função usa `get_text("dict")` para obter cada linha com bbox; depois
    identifica linhas que são apenas dígitos (margens) e funde-as in-line com
    a linha de corpo cujo Y é mais próximo. O output fica:

        ...
        ao grosso volume do romance...
        5 perder-se numa das mais perfeitas...    ← marcador alinhado com a linha 5
        ...
    """
    data = page.get_text("dict")
    lines: list[dict] = []
    for block in data.get("blocks", []):
        if block.get("type", 0) != 0:  # 0 = bloco de texto
            continue
        for line in block.get("lines", []):
            txt = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
            if not txt:
                continue
            x0, y0, x1, y1 = line["bbox"]
            lines.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": txt})

    # Separar marcadores: dígitos puros + largura pequena (filtra "5" inline em texto).
    margin = [
        l for l in lines
        if _MARGIN_NUM_RE.match(l["text"]) and (l["x1"] - l["x0"]) < _MARGIN_LINE_MAX_WIDTH
    ]
    body = [l for l in lines if l not in margin]

    # Anexar cada marcador à linha de corpo com Y mais próximo (tolerância
    # = altura do próprio marcador ou 8pt, o que for maior).
    for m in margin:
        my = (m["y0"] + m["y1"]) / 2
        best, best_dy = None, None
        for b in body:
            dy = abs((b["y0"] + b["y1"]) / 2 - my)
            if best_dy is None or dy < best_dy:
                best, best_dy = b, dy
        tol = max(m["y1"] - m["y0"], 8.0)
        if best is not None and best_dy is not None and best_dy <= tol:
            best["text"] = f"{m['text']} {best['text']}"
        else:
            # Sem linha de corpo próxima — manter como linha solta.
            body.append(m)

    body.sort(key=lambda l: (round(l["y0"], 1), round(l["x0"], 1)))
    return "\n".join(l["text"] for l in body)


def prepare_pages(
    pdf_path: Path,
    workspace_dir: Path,
    *,
    pages: list[int] | None = None,
    dpi: int = 200,
) -> dict:
    """Renderiza PNG + extrai texto PyMuPDF para cada página marcada como manter.

    Lê `triage/pages_manifest.json` se `pages` não for explicitado. Output em
    `pages/page_NNN.png` e `pages/page_NNN.txt`. Devolve metadata.
    """
    import fitz  # noqa: PLC0415

    if pages is None:
        manifest_path = workspace_dir / "triage" / "pages_manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"Manifesto não encontrado: {manifest_path}. Correr `triage` primeiro."
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pages = sorted(manifest["pages_to_process"])

    pages_dir = workspace_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    rendered: list[dict] = []
    for page_num in pages:
        if not (1 <= page_num <= len(doc)):
            continue
        page = doc[page_num - 1]
        png_path = pages_dir / f"page_{page_num:03d}.png"
        txt_path = pages_dir / f"page_{page_num:03d}.txt"

        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pix.save(str(png_path))

        text = _extract_text_with_inline_margin_numbers(page)
        txt_path.write_text(text, encoding="utf-8")

        rendered.append({
            "page": page_num,
            "png": png_path.name,
            "txt": txt_path.name,
            "png_size_kb": round(png_path.stat().st_size / 1024, 1),
            "txt_chars": len(text),
        })
    doc.close()

    meta = {
        "pdf_path": str(pdf_path),
        "dpi": dpi,
        "total_pages": len(rendered),
        "pages": rendered,
    }
    (pages_dir / "prepared.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


# ── Top-level ────────────────────────────────────────────────────────────────

def triage_pdf(
    pdf_path: Path,
    output_dir: Path,
    *,
    kind: str = "auto",
    contact_sheet: bool = True,
    contact_sheet_dpi: int = 80,
) -> TriageResult:
    """Executa a triagem completa: heurística textual + contact sheet + manifesto."""
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    if kind == "auto":
        kind = detect_kind(pdf_path)

    result = triage_textual(pdf_path, kind=kind)

    output_dir.mkdir(parents=True, exist_ok=True)

    if contact_sheet:
        sheet_path = output_dir / "contact_sheet.png"
        try:
            render_contact_sheet(
                pdf_path, sheet_path,
                excluded=result.pages_excluded,
                dpi=contact_sheet_dpi,
            )
            result.contact_sheet_path = sheet_path
        except Exception as exc:
            result.notes.append(f"contact sheet falhou: {exc}")

    manifest_path = output_dir / "pages_manifest.json"
    manifest_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    result.manifest_path = manifest_path
    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def _main() -> int:
    parser = argparse.ArgumentParser(description="Triagem de páginas de um PDF.")
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Directório de output (default: workspace/<NOME>/triage).")
    parser.add_argument("--workspace", type=str, default=None,
                        help="Nome do workspace. Default: stem do PDF.")
    parser.add_argument("--kind", choices=["auto", "cc", "prova"], default="auto")
    parser.add_argument("--no-contact-sheet", action="store_true")
    parser.add_argument("--dpi", type=int, default=80, help="DPI das thumbnails.")
    args = parser.parse_args()

    pdf_path = args.pdf_path.resolve()
    if args.output_dir:
        output_dir = args.output_dir.resolve()
    else:
        from .config import load_settings  # noqa: PLC0415
        settings = load_settings()
        ws_name = args.workspace or pdf_path.stem
        output_dir = settings.workdir / ws_name / "triage"

    result = triage_pdf(
        pdf_path, output_dir,
        kind=args.kind,
        contact_sheet=not args.no_contact_sheet,
        contact_sheet_dpi=args.dpi,
    )

    print(f"📄 {pdf_path.name}  ({result.total_pages} páginas)")
    print(f"   tipo: {result.kind}   método: {result.method}   confiança: {result.confidence}")
    keep = result.pages_to_process
    if len(keep) <= 30:
        keep_str = ", ".join(map(str, keep))
    else:
        keep_str = f"{keep[0]}–{keep[-1]} ({len(keep)})"
    print(f"   manter: [{keep_str}]")
    if result.pages_excluded:
        print(f"   excluir ({len(result.pages_excluded)}):")
        for p in sorted(result.pages_excluded):
            print(f"     p{p}: {result.pages_excluded[p]}")
    for note in result.notes:
        print(f"   ⚠️  {note}")
    print(f"   manifesto: {result.manifest_path}")
    if result.contact_sheet_path:
        print(f"   contact sheet: {result.contact_sheet_path}")
    if result.needs_review:
        print("   🔎 needs_review=true — abrir contact sheet e ajustar pages_to_process se necessário.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
