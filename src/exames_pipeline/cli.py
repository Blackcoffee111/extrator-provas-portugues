from __future__ import annotations

import argparse
from pathlib import Path

from .cc_extract import extract_cc
from .cc_merge import merge_cc
from .cc_validate import validate_criterios
from .config import load_settings
from .module_categorize import categorize_questions
from .module_cotacoes import extract_cotacoes_estrutura
from .module_micro_lint import run_micro_lint
from .module_preprocess import preprocess_pdf_for_ocr
from .module_preview import run_preview
from .module_structure import structure_markdown
from .module_validate import validate_questions
from .pdf_parser import extract_pdf
from .utils import infer_fonte_from_path
from .supabase_client import upload_to_supabase


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pipeline de exames nacionais.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preprocess_parser = subparsers.add_parser(
        "preprocess",
        help="Módulo 0.5: pré-processa o PDF (contraste + sharpening) antes do OCR.",
    )
    preprocess_parser.add_argument("pdf_path", type=Path)
    preprocess_parser.add_argument("--dpi", type=int, default=300)
    preprocess_parser.add_argument("--brightness", type=float, default=1.4,
                                   dest="brightness_factor",
                                   help="Factor de brilho (default 1.4).")
    preprocess_parser.add_argument("--contrast", type=float, default=2.5,
                                   dest="contrast_factor",
                                   help="Factor de contraste (default 2.5).")
    preprocess_parser.add_argument("--scale", type=float, default=1.0,
                                   dest="page_scale",
                                   help="Escala das páginas no PDF de saída (default 1.0; 2.0 = zoom 2×).")
    preprocess_parser.add_argument("--skip-pages", type=int, default=0,
                                   dest="skip_first_pages",
                                   help="Número de páginas iniciais a omitir (default 0).")
    preprocess_parser.add_argument("--force", action="store_true",
                                   help="Forçar re-processamento mesmo se já existe.")

    extract_parser = subparsers.add_parser("extract", help="Extrai markdown e imagens de um PDF.")
    extract_parser.add_argument("pdf_path", type=Path)
    extract_parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Nome do workspace de saída. Se omitido, usa o nome do PDF.",
    )
    extract_parser.add_argument("--start-page", type=int, default=None)
    extract_parser.add_argument("--end-page", type=int, default=None)
    extract_parser.add_argument("--mineru-mode", choices=["light", "full", "math_heavy"], default=None)
    extract_parser.add_argument("--no-preprocess", action="store_true",
                                help="Desactivar o pré-processamento (módulo 0.5).")

    structure_parser = subparsers.add_parser("structure", help="Estrutura markdown em JSON base.")
    structure_parser.add_argument("markdown_path", type=Path)
    structure_parser.add_argument(
        "--fonte",
        type=str,
        default="",
        help='Descrição legível da prova (ex: "Exame Nacional, Matemática A, 1.ª Fase, 2024"). '
             "Se omitido, é inferida automaticamente do nome do ficheiro.",
    )

    cotacoes_parser = subparsers.add_parser(
        "extract-cotacoes-structure",
        help="Extrai a estrutura da prova a partir da tabela de cotações (requer modelo de visão).",
    )
    cotacoes_parser.add_argument(
        "markdown_path",
        type=Path,
        help="Caminho para o prova.md gerado pelo Módulo 1.",
    )

    validate_parser = subparsers.add_parser("validate", help="Valida o JSON bruto.")
    validate_parser.add_argument("raw_json_path", type=Path)

    micro_lint_parser = subparsers.add_parser(
        "micro-lint",
        help="Aplica micro-lint a todas as questões extraídas antes do validate.",
    )
    micro_lint_parser.add_argument("raw_json_path", type=Path)

    subparsers.add_parser(
        "backup",
        help="Faz backup local de todas as tabelas e imagens do Supabase.",
    )

    answer_key_extract_parser = subparsers.add_parser(
        "extract-answer-key",
        help="Extrai um gabarito simples de markdown para JSON.",
    )
    answer_key_extract_parser.add_argument("answer_key_markdown", type=Path)

    merge_parser = subparsers.add_parser("merge-answer-key", help="Faz o merge do gabarito.")
    merge_parser.add_argument("approved_json_path", type=Path)
    merge_parser.add_argument("answer_key_json_path", type=Path)

    upload_parser = subparsers.add_parser("upload", help="Faz upload para Supabase.")
    upload_parser.add_argument("final_json_path", type=Path)
    upload_parser.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Simula o upload sem enviar dados — mostra o que seria feito.",
    )

    preview_parser = subparsers.add_parser("preview", help="Abre preview interativo das questões aprovadas.")
    preview_parser.add_argument("approved_json_path", type=Path)
    preview_parser.add_argument(
        "--port", type=int, default=8798,
        help="Porta do servidor HTTP local (default: 8798).",
    )
    preview_parser.add_argument("--output", type=Path, default=None, help="Caminho do ficheiro questoes_revisao.json.")

    categorize_parser = subparsers.add_parser(
        "categorize",
        help="Categoriza questões aprovadas com tópico, subtópico e descrição breve (Módulo 5).",
    )
    categorize_parser.add_argument("approved_json_path", type=Path)

    # ── Workflow CC-VD (critérios de classificação) ─────────────────────────

    cc_extract_parser = subparsers.add_parser(
        "cc-extract",
        help="CC: extrai critérios do markdown CC-VD e gera rascunhos + chunks de revisão.",
    )
    cc_extract_parser.add_argument(
        "markdown_path",
        type=Path,
        help="Caminho para o prova.md gerado por 'extract <cc_pdf> --no-preprocess'.",
    )
    cc_extract_parser.add_argument(
        "--fonte", type=str, default="",
        help="Identificador da prova (ex: 'EX-MatA635-F1-2023-CC-VD'). "
             "Inferido automaticamente se omitido.",
    )
    cc_extract_parser.add_argument(
        "--questoes-review", type=Path, default=None, dest="questoes_review_path",
        help="Caminho para questoes_review.json do workspace principal. "
             "Usado para cruzar tipo_item: multi_select/complete_table/essay nunca são "
             "classificados como multiple_choice (evita contaminação OCR).",
    )

    cc_validate_parser = subparsers.add_parser(
        "cc-validate",
        help="CC: valida criterios_raw.json após revisão em lote do agente.",
    )
    cc_validate_parser.add_argument("criterios_raw_path", type=Path)

    cc_merge_parser = subparsers.add_parser(
        "cc-merge",
        help="CC: junta criterios_aprovados.json com questoes_aprovadas.json.",
    )
    cc_merge_parser.add_argument("criterios_aprovados_path", type=Path)
    cc_merge_parser.add_argument("questoes_aprovadas_path", type=Path)
    cc_merge_parser.add_argument(
        "--force",
        action="store_true",
        help="Incluir apenas os itens fundidos e ignorar pendentes (sem critério/mismatch/contaminação).",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    settings = load_settings(Path.cwd())

    if args.command == "preprocess":
        from pathlib import Path as _Path
        pdf_path = args.pdf_path.resolve()
        output_dir = settings.workdir / pdf_path.stem
        output_dir.mkdir(parents=True, exist_ok=True)
        result_path = preprocess_pdf_for_ocr(
            pdf_path,
            output_dir,
            dpi=args.dpi,
            brightness_factor=args.brightness_factor,
            contrast_factor=args.contrast_factor,
            page_scale=args.page_scale,
            skip_first_pages=args.skip_first_pages,
            force=args.force,
        )
        print(result_path)
        return

    if args.command == "extract":
        result = extract_pdf(
            settings,
            args.pdf_path,
            workspace_name=args.workspace,
            start_page=args.start_page,
            end_page=args.end_page,
            mineru_mode=args.mineru_mode,
            preprocess=not args.no_preprocess,
        )
        print(result.markdown_path)
        if result.parser_stdout:
            print(result.parser_stdout)
        if result.parser_stderr:
            print(result.parser_stderr)

        # Módulo 1.5: Extrai automaticamente a tabela de cotações (se existir)
        print("\n[pipeline] Extraindo tabela de cotações...")
        cotacoes_path = extract_cotacoes_estrutura(settings, result.markdown_path)
        if cotacoes_path:
            print(f"[pipeline] ✅ Cotações extraídas → {cotacoes_path}")
        else:
            print("[pipeline] ⚠️  Tabela de cotações não detectada ou sem credenciais.")

        fonte = infer_fonte_from_path(result.markdown_path)
        if fonte:
            print(f"[pipeline] Estruturando questões com fonte inferida: {fonte}")
        raw_json_path = structure_markdown(settings, result.markdown_path, fonte=fonte)
        print(f"[pipeline] ✅ Questões estruturadas → {raw_json_path}")
        return

    if args.command == "structure":
        fonte = args.fonte or infer_fonte_from_path(args.markdown_path)
        if not fonte:
            print(f"[aviso] Não foi possível inferir 'fonte' a partir de '{args.markdown_path.name}'. "
                  "Use --fonte para definir manualmente.")
        else:
            print(f"[fonte] {fonte}")
        output = structure_markdown(settings, args.markdown_path, fonte=fonte)
        print(output)
        return

    if args.command == "extract-cotacoes-structure":
        output = extract_cotacoes_estrutura(settings, args.markdown_path)
        if output:
            print(output)
        else:
            print("Tabela de cotações não detectada ou sem credenciais disponíveis.")
        return

    if args.command == "validate":
        approved_path, rejected_path = validate_questions(args.raw_json_path)
        print(approved_path)
        print(rejected_path)
        return

    if args.command == "micro-lint":
        output = run_micro_lint(args.raw_json_path)
        print(output)
        return

    if args.command == "extract-answer-key":
        from .module_answer_key import extract_answer_key  # noqa: PLC0415
        output = extract_answer_key(args.answer_key_markdown)
        print(output)
        return

    if args.command == "merge-answer-key":
        from .module_answer_key import merge_answer_key  # noqa: PLC0415
        output = merge_answer_key(args.approved_json_path, args.answer_key_json_path)
        print(output)
        return

    if args.command == "backup":
        from .module_backup import run_backup
        meta_path = run_backup(settings)
        print(meta_path)
        return

    if args.command == "upload":
        summary = upload_to_supabase(settings, args.final_json_path, dry_run=args.dry_run)
        status = "DRY-RUN" if summary.dry_run else "OK"
        print(f"\n[resultado] status={status} "
              f"imagens={len(summary.uploaded_images)} "
              f"upserted={summary.upserted_rows} "
              f"skipped={summary.skipped_rows} "
              f"erros={len(summary.errors)}")
        if summary.errors:
            for err in summary.errors[:10]:
                print(f"  ❌ {err}")
        return

    if args.command == "categorize":
        output = categorize_questions(settings, args.approved_json_path)
        print(output)
        return

    if args.command == "preview":
        output = run_preview(args.approved_json_path, args.output, port=args.port)
        print(output)
        return

    # ── Workflow CC-VD ────────────────────────────────────────────────────────

    if args.command == "cc-extract":
        fonte = args.fonte or infer_fonte_from_path(args.markdown_path)
        output = extract_cc(
            settings,
            args.markdown_path,
            fonte=fonte,
            questoes_review_path=args.questoes_review_path,
        )
        print(output)
        return

    if args.command == "cc-validate":
        approved_path, rejected_path = validate_criterios(args.criterios_raw_path)
        print(approved_path)
        print(rejected_path)
        return

    if args.command == "cc-merge":
        output = merge_cc(args.criterios_aprovados_path, args.questoes_aprovadas_path, force=args.force)
        print(output)
        return


if __name__ == "__main__":
    main()
