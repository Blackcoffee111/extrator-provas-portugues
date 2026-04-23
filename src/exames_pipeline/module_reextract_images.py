"""
Módulo: re-extração de imagens do PDF original.

Substitui as imagens em `imagens_extraidas/` (recortadas pelo MinerU a partir
do PDF pré-processado, logo com brilho/contraste artificiais) por recortes
frescos do PDF original, usando os bounding boxes que o MinerU já gravou em
`_middle.json`.

Nomes dos ficheiros são **preservados** — o hash SHA-256 continua a ser o
identificador usado pelas referências em `prova.md` e nos JSONs; nada mais
precisa ser reescrito.

Um backup da pasta original é criado em `imagens_extraidas.pre_reextract/` na
primeira vez que este módulo é corrido — permite reverter e serve como
fonte-da-verdade-do-que-havia-antes em execuções repetidas.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DPI = 220
DEFAULT_PADDING_PT = 4.0
BACKUP_DIRNAME = "imagens_extraidas.pre_reextract"


@dataclass
class ReextractResult:
    workspace: str
    processed: int
    skipped_missing_name: int
    skipped_missing_current: int
    backup_created: bool
    message: str


def _load_middle_and_content_list(workspace_dir: Path) -> tuple[dict, list]:
    ocr_dir = workspace_dir / "preprocessed_input" / "ocr"
    candidates_middle = list(ocr_dir.glob("*_middle.json"))
    candidates_content = list(ocr_dir.glob("*_content_list.json"))
    if not candidates_middle or not candidates_content:
        raise FileNotFoundError(
            f"Ficheiros do MinerU não encontrados em {ocr_dir} "
            "(procurando *_middle.json e *_content_list.json)."
        )
    middle = json.loads(candidates_middle[0].read_text())
    content_list = json.loads(candidates_content[0].read_text())
    return middle, content_list


def _collect_blocks(middle: dict, content_list: list) -> list[dict]:
    """Cruza middle.json (bbox em pt) com content_list.json (nomes de ficheiro).

    Correspondência por ordem de aparição dentro de (page_idx, type).
    """
    img_names: dict[tuple[int, str], list[str]] = {}
    for entry in content_list:
        t = entry.get("type")
        if t in ("image", "table"):
            key = (entry["page_idx"], t)
            img_names.setdefault(key, []).append(Path(entry["img_path"]).name)

    blocks: list[dict] = []
    for page in middle.get("pdf_info", []):
        page_idx = page["page_idx"]
        page_size = page.get("page_size")
        counters: dict[str, int] = {"image": 0, "table": 0}
        for block in page.get("para_blocks", []):
            t = block.get("type")
            if t not in ("image", "table"):
                continue
            bucket = img_names.get((page_idx, t), [])
            idx = counters[t]
            counters[t] += 1
            name = bucket[idx] if idx < len(bucket) else None
            blocks.append({
                "page_idx": page_idx,
                "type": t,
                "bbox_pt": block["bbox"],
                "page_size": page_size,
                "img_name": name,
            })
    return blocks


def _assert_same_page_dims(original_pdf: Path, preprocessed_pdf: Path) -> None:
    """Aborta se dimensões/nº de páginas divergirem (page_scale ≠ 1.0 ou skip_first_pages > 0)."""
    import fitz  # type: ignore[import]

    with fitz.open(str(original_pdf)) as a, fitz.open(str(preprocessed_pdf)) as b:
        if len(a) != len(b):
            raise ValueError(
                f"Nº de páginas difere: original={len(a)} preprocessed={len(b)}. "
                "Provavelmente o preprocess foi corrido com skip_first_pages>0. "
                "Re-extração automática não é segura; executar manualmente."
            )
        for i in range(len(a)):
            ra, rb = a[i].rect, b[i].rect
            if abs(ra.width - rb.width) > 0.5 or abs(ra.height - rb.height) > 0.5:
                raise ValueError(
                    f"Dimensões da página {i} diferem: "
                    f"original={ra.width:.1f}x{ra.height:.1f} "
                    f"preprocessed={rb.width:.1f}x{rb.height:.1f}. "
                    "Provavelmente o preprocess foi corrido com page_scale≠1.0."
                )


def reextract_images(
    workspace_dir: Path,
    original_pdf: Path,
    *,
    dpi: int = DEFAULT_DPI,
    padding_pt: float = DEFAULT_PADDING_PT,
    make_backup: bool = True,
    verbose: bool = True,
) -> ReextractResult:
    """Recorta imagens do PDF original e sobrescreve `imagens_extraidas/`.

    Pré-condições:
      - `workspace_dir/preprocessed_input/ocr/*_middle.json` existe
      - `workspace_dir/preprocessed_input/ocr/*_content_list.json` existe
      - `workspace_dir/preprocessed_input.pdf` existe (para validar dimensões)
      - `original_pdf` existe e tem as mesmas dimensões do preprocessed
    """
    try:
        import fitz  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError("pymupdf não instalado — `pip install pymupdf`.") from exc

    workspace_dir = Path(workspace_dir)
    original_pdf = Path(original_pdf)

    if not original_pdf.exists():
        raise FileNotFoundError(f"PDF original não encontrado: {original_pdf}")

    preprocessed_pdf = workspace_dir / "preprocessed_input.pdf"
    if preprocessed_pdf.exists():
        _assert_same_page_dims(original_pdf, preprocessed_pdf)

    middle, content_list = _load_middle_and_content_list(workspace_dir)
    blocks = _collect_blocks(middle, content_list)

    images_dir = workspace_dir / "imagens_extraidas"
    if not images_dir.exists():
        raise FileNotFoundError(f"Pasta `imagens_extraidas/` não existe em {workspace_dir}")

    backup_dir = workspace_dir / BACKUP_DIRNAME
    backup_created = False
    if make_backup and not backup_dir.exists():
        shutil.copytree(images_dir, backup_dir)
        backup_created = True
        if verbose:
            print(f"[reextract] 💾 Backup criado → {backup_dir.name}/")

    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    processed = 0
    skipped_missing_name = 0
    skipped_missing_current = 0

    with fitz.open(str(original_pdf)) as doc:
        for b in blocks:
            name = b["img_name"]
            if name is None:
                skipped_missing_name += 1
                if verbose:
                    print(f"[reextract] ⚠️  sem img_path para {b['type']} na pág {b['page_idx']+1}")
                continue

            target = images_dir / name
            if not target.exists():
                skipped_missing_current += 1
                if verbose:
                    print(f"[reextract] ⚠️  imagem atual ausente: {name}")
                continue

            page = doc[b["page_idx"]]
            x0, y0, x1, y1 = b["bbox_pt"]
            clip = fitz.Rect(
                max(0, x0 - padding_pt),
                max(0, y0 - padding_pt),
                min(page.rect.width, x1 + padding_pt),
                min(page.rect.height, y1 + padding_pt),
            )
            pix = page.get_pixmap(clip=clip, matrix=matrix, alpha=False)
            pix.save(str(target))
            processed += 1
            if verbose:
                print(
                    f"[reextract]   {b['type']:5s} pág {b['page_idx']+1}  "
                    f"→ {name[:16]}… ({pix.width}x{pix.height})"
                )

    msg_parts = [f"✅ {processed} imagem(ns) re-extraída(s) do PDF original"]
    if skipped_missing_name:
        msg_parts.append(f"{skipped_missing_name} sem nome no content_list")
    if skipped_missing_current:
        msg_parts.append(f"{skipped_missing_current} sem imagem atual correspondente")
    message = " — ".join(msg_parts) + f" (DPI={dpi}, padding={padding_pt}pt)"

    return ReextractResult(
        workspace=workspace_dir.name,
        processed=processed,
        skipped_missing_name=skipped_missing_name,
        skipped_missing_current=skipped_missing_current,
        backup_created=backup_created,
        message=message,
    )
