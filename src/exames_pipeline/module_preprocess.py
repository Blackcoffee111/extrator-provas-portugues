"""
Módulo 0.5 — Pré-processamento de PDF para OCR.

Antes do MinerU processar o PDF, este módulo:
  1. Renderiza cada página a DPI elevado (default 300 DPI)
  2. Aumenta o contraste globalmente
  3. Aplica unsharp mask para realçar bordas de caracteres
  4. Reconstrói um PDF com as imagens processadas

O resultado é um PDF com texto visualmente mais nítido, especialmente útil para
caixas com fundo cinzento onde o número de questão fica de difícil leitura pelo OCR.

Dependências: pymupdf (fitz) e Pillow.
Se alguma estiver ausente, a função devolve o PDF original inalterado.
"""
from __future__ import annotations

import io
from pathlib import Path


# ---------------------------------------------------------------------------
# Ponto de entrada principal
# ---------------------------------------------------------------------------

def preprocess_pdf_for_ocr(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = 300,
    brightness_factor: float = 1.4,
    contrast_factor: float = 2.5,
    unsharp_radius: float = 2.0,
    unsharp_percent: int = 150,
    unsharp_threshold: int = 3,
    page_scale: float = 1.0,
    skip_first_pages: int = 0,
    force: bool = False,
) -> Path:
    """
    Pré-processa o PDF para melhorar a qualidade do OCR do MinerU.

    Pipeline de processamento por página:
      1. Renderizar a DPI elevado
      2. Aumentar brilho  (clareia o fundo cinzento antes de esticar o contraste)
      3. Aumentar contraste (afasta o texto escuro do fundo agora mais claro)
      4. Unsharp mask      (realça bordas dos caracteres)

    Parâmetros
    ----------
    brightness_factor  : Factor de brilho (1.0 = original; 1.4 = 40% mais brilhante).
                         Aplicado antes do contraste para clarear fundos cinzentos.
    contrast_factor    : Factor de contraste (1.0 = original; 2.5 = mais que duplica).
    page_scale         : Escala das páginas no PDF de saída (1.0 = tamanho original;
                         2.0 = páginas 2× maiores). Útil para inspecção visual ou
                         para forçar MinerU a trabalhar com texto maior.
    skip_first_pages   : Número de páginas iniciais a omitir do PDF de saída (default 0).
                         Útil para saltar capa e formulário, que não contêm questões
                         e podem confundir o OCR.
    """
    output_path = output_dir / "preprocessed_input.pdf"

    if not force and output_path.exists():
        if output_path.stat().st_mtime >= pdf_path.stat().st_mtime:
            print(f"[preprocess] PDF pré-processado já existe — a reutilizar ({output_path.name}).")
            return output_path

    try:
        import fitz  # type: ignore[import]
    except ImportError:
        print("[preprocess] ⚠️  pymupdf não instalado — a usar PDF original.")
        return pdf_path

    try:
        from PIL import Image, ImageEnhance, ImageFilter  # type: ignore[import]
    except ImportError:
        print("[preprocess] ⚠️  Pillow não instalado — a usar PDF original.")
        return pdf_path

    skip = max(0, skip_first_pages)
    print(
        f"[preprocess] A pré-processar '{pdf_path.name}' "
        f"({dpi} DPI  brilho ×{brightness_factor}  contraste ×{contrast_factor}"
        + (f"  a saltar primeiras {skip} pág." if skip else "") + ") ..."
    )

    try:
        src_doc = fitz.open(str(pdf_path))
        new_doc = fitz.open()
        matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)

        for page_num in range(len(src_doc)):
            if page_num < skip:
                print(f"[preprocess]   página {page_num + 1}/{len(src_doc)} ignorada (skip_first_pages={skip}).")
                continue
            page = src_doc[page_num]

            # 1. Renderizar página a DPI elevado
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            # 2. Converter para imagem PIL
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            # 3. Brilho — clareia o fundo cinzento antes de esticar o contraste.
            #    Aplicado primeiro para que o contraste trabalhe sobre pixels já mais claros.
            if brightness_factor != 1.0:
                img = ImageEnhance.Brightness(img).enhance(brightness_factor)

            # 4. Contraste — afasta o texto escuro (agora ainda mais escuro relativo)
            #    do fundo agora mais claro.
            if contrast_factor != 1.0:
                img = ImageEnhance.Contrast(img).enhance(contrast_factor)

            # 5. Unsharp mask — realça bordas de caracteres sem introduzir artefactos
            img = img.filter(
                ImageFilter.UnsharpMask(
                    radius=unsharp_radius,
                    percent=unsharp_percent,
                    threshold=unsharp_threshold,
                )
            )

            # 6. Serializar para PNG e inserir na nova página
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=False)
            new_page = new_doc.new_page(
                width=page.rect.width * page_scale,
                height=page.rect.height * page_scale,
            )
            new_page.insert_image(new_page.rect, stream=buf.getvalue())

            print(f"[preprocess]   página {page_num + 1}/{len(src_doc)} processada.")

        src_doc.close()
        output_dir.mkdir(parents=True, exist_ok=True)
        new_doc.save(str(output_path), garbage=4, deflate=True)
        new_doc.close()

        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"[preprocess] ✅ PDF processado → {output_path} ({size_mb:.1f} MB)")
        return output_path

    except Exception as exc:
        print(f"[preprocess] ❌ Erro no pré-processamento: {exc} — a usar PDF original.")
        return pdf_path
