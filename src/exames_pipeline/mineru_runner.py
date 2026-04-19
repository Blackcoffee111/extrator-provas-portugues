from __future__ import annotations

import os
import sys


def _force_xycut_without_site_patch() -> None:
    if os.environ.get("MINERU_DISABLE_LAYOUTREADER", "0") != "1":
        return

    import mineru.utils.block_sort as block_sort

    def _sort_lines_by_xycut(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    block_sort.sort_lines_by_model = _sort_lines_by_xycut


def _force_single_process_pdf_render() -> None:
    if os.environ.get("MINERU_SINGLE_PROCESS_RENDER", "0") != "1":
        return

    import mineru.utils.pdf_image_tools as pdf_image_tools

    def _load_images_without_process_pool(  # type: ignore[no-untyped-def]
        pdf_bytes,
        dpi=200,
        start_page_id=0,
        end_page_id=None,
        image_type=None,
        timeout=None,
        threads=None,
    ):
        pdf_doc = pdf_image_tools.pdfium.PdfDocument(pdf_bytes)
        last_page = pdf_image_tools.get_end_page_id(end_page_id, len(pdf_doc))
        images_list = pdf_image_tools.load_images_from_pdf_core(
            pdf_bytes,
            dpi,
            start_page_id,
            last_page,
            image_type or pdf_image_tools.ImageType.PIL,
        )
        return images_list, pdf_doc

    pdf_image_tools.load_images_from_pdf = _load_images_without_process_pool


def main() -> int:
    _force_xycut_without_site_patch()
    _force_single_process_pdf_render()

    from mineru.cli.client import main as mineru_main

    try:
        result = mineru_main(standalone_mode=False)
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 1
    return int(result or 0)


if __name__ == "__main__":
    sys.exit(main())
