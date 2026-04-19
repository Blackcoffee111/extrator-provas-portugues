"""MCP Server — Exames Nacionais Pipeline (P3: superfície reduzida a 5 tools).

Ferramentas expostas:
  list_workspaces()           — lista workspaces e estado resumido de cada um
  workspace_status(workspace) — estado detalhado + próxima acção sugerida
  run_stage(workspace, stage) — executa um estágio do pipeline
  run_review(workspace)       — abre preview interactivo para revisão humana
  run_fix_question(...)       — correcção pontual de um campo pós-revisão

Stages de run_stage:
  extract   — OCR (MinerU) + cotações + estruturação
  validate  — micro-lint interno + validação heurística
  cc        — critérios CC-VD: 1ª chamada → cc_extract; 2ª chamada → cc_validate
  merge     — cc_merge + abre preview
  upload    — upload Supabase + backup automático
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .module_categorize import check_all_categorized
from .workspace_state import WorkspaceStage

# ── Configuração ──────────────────────────────────────────────────────────────

_REPO_DIR = Path(os.environ.get("PIPELINE_ROOT", Path(__file__).parent.parent.parent))
_WORKSPACE_DIR = _REPO_DIR / "workspace"
_PYTHON = os.environ.get("PIPELINE_PYTHON", "/opt/homebrew/bin/python3.11")
_PKG = "exames_pipeline.cli"

mcp = FastMCP(
    "Exames Nacionais Pipeline",
    instructions=(
        "Pipeline: extrair → validar → CC-VD → merge → upload questões para Supabase.\n\n"
        "Estados: fresh → extracted → validated → cc_merged → human_approved → uploaded\n"
        "CC sub-pipeline (workspace separado): cc_fresh → cc_extracted → cc_validated\n\n"
        "Tools: list_workspaces | workspace_status | run_stage | run_review | run_fix_question\n"
        "Stages de run_stage: extract | validate | cc (×2) | merge | upload\n\n"
        "⚠️ MinerU deve correr fora do sandbox (Terminal). Se extract falhar, correr MinerU\n"
        "   manualmente, copiar prova.md + images/ para o workspace e chamar extract sem pdf_path.\n"
        "⚠️ Nunca re-extrair/re-validar após edições. Correções pontuais: run_fix_question.\n"
        "   Em dúvida, chamar workspace_status() primeiro."
    ),
)


# ── Helpers internos ──────────────────────────────────────────────────────────

def _run(args: list[str], cwd: Path | None = None) -> dict[str, Any]:
    """Corre um subcomando do pipeline e devolve {ok, stdout, stderr, returncode}."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_REPO_DIR / "src")
    env["PIPELINE_ROOT"] = str(_REPO_DIR)
    cmd = [_PYTHON, "-m", _PKG] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd or _REPO_DIR),
            env=env,
            timeout=300,
        )
        return {
            "ok":         result.returncode == 0,
            "stdout":     result.stdout.strip(),
            "stderr":     result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "Timeout (300s)", "returncode": -1}
    except Exception as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc), "returncode": -1}


def _workspace_path(workspace_name: str) -> Path:
    return _WORKSPACE_DIR / workspace_name


def _file_exists(workspace: str, filename: str) -> bool:
    return (_workspace_path(workspace) / filename).exists()


def _count_json(workspace: str, filename: str) -> int | None:
    path = _workspace_path(workspace) / filename
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return len(data) if isinstance(data, list) else None
    except Exception:
        return None


def _count_reviewed(workspace: str) -> tuple[int, int] | None:
    """Devolve (reviewed, total) para questoes_raw.json, ou None se não existir."""
    path = _workspace_path(workspace) / "questoes_raw.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return None
        total = len(data)
        reviewed = sum(1 for q in data if isinstance(q, dict) and q.get("reviewed"))
        return reviewed, total
    except Exception:
        return None


def _find_cc_workspace(workspace: str) -> str | None:
    """Tenta detectar automaticamente o workspace CC-VD associado pelo prefixo comum."""
    if not _WORKSPACE_DIR.exists():
        return None
    candidates = []
    for d in _WORKSPACE_DIR.iterdir():
        if not d.is_dir() or d.name == workspace:
            continue
        name_upper = d.name.upper()
        if "CC" in name_upper or "VD" in name_upper:
            common = len(os.path.commonprefix([workspace, d.name]))
            candidates.append((common, d.name))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _workspace_state(ws_dir: Path) -> dict[str, Any]:
    """Devolve o estado resumido de um workspace como dict."""
    name = ws_dir.name
    files = {f.name for f in ws_dir.iterdir()} if ws_dir.exists() else set()
    return {
        "nome":               name,
        "prova_md":           "prova.md" in files,
        "questoes_raw":       _count_json(name, "questoes_raw.json"),
        "questoes_aprovadas": _count_json(name, "questoes_aprovadas.json"),
        "questoes_com_erro":  _count_json(name, "questoes_com_erro.json"),
        "questoes_final":     _count_json(name, "questoes_final.json"),
        "criterios_aprovados":_count_json(name, "criterios_aprovados.json"),
        "upload_done":        _file_exists(name, ".upload_done"),
    }


def _next_action(ws_dir: Path, workspace: str) -> str:
    """Determina a próxima acção sugerida com base no estado actual do workspace."""
    ws = WorkspaceStage(ws_dir)
    stage = ws.stage

    if stage == "uploaded":
        return "✅ Pipeline concluído — questões publicadas no Supabase."

    if stage == "human_approved":
        return f"run_stage(workspace='{workspace}', stage='upload')"

    if stage == "cc_merged":
        return (
            f"run_review(workspace='{workspace}') — abrir preview e aguardar aprovação humana\n"
            f"  Depois: run_stage(workspace='{workspace}', stage='upload')"
        )

    if stage == "validated":
        cc_ws = _find_cc_workspace(workspace)
        if cc_ws:
            cc_dir = _workspace_path(cc_ws)
            cc_st = WorkspaceStage(cc_dir).cc_stage
            if cc_st == "cc_validated":
                return f"run_stage(workspace='{workspace}', stage='merge', workspace_cc='{cc_ws}')"
            if cc_st == "cc_extracted":
                return (
                    f"Rever criterios_raw.json em '{cc_ws}' (reviewed:true em cada item),\n"
                    f"  depois run_stage(workspace='{workspace}', stage='cc', workspace_cc='{cc_ws}')"
                )
            cc_prova = cc_dir / "prova.md"
            if not cc_prova.exists():
                return (
                    f"Correr MinerU no PDF CC-VD → copiar prova.md para workspace/{cc_ws}/prova.md,\n"
                    f"  depois run_stage(workspace='{workspace}', stage='cc', workspace_cc='{cc_ws}')"
                )
            return f"run_stage(workspace='{workspace}', stage='cc', workspace_cc='{cc_ws}')"
        # Sem CC-VD detectado → ir directamente para revisão + upload
        return (
            f"run_review(workspace='{workspace}') — sem CC-VD detectado, aprovar directamente\n"
            f"  Depois: run_stage(workspace='{workspace}', stage='upload')\n"
            f"  (Se houver CC-VD: run_stage(stage='cc', workspace_cc='<NOME-CC-VD>'))"
        )

    if stage == "extracted":
        rev = _count_reviewed(workspace)
        if rev:
            reviewed, total = rev
            if reviewed < total:
                return (
                    f"Rever questoes_raw.json ({reviewed}/{total} revistos — "
                    f"{total - reviewed} pendentes: reviewed:true + categorização),\n"
                    f"  depois run_stage(workspace='{workspace}', stage='validate')"
                )
        return f"run_stage(workspace='{workspace}', stage='validate')"

    # fresh
    return f"run_stage(workspace='{workspace}', stage='extract', pdf_path='<CAMINHO_ABSOLUTO_PDF>')"


def _format_result(step: str, result: dict[str, Any]) -> str:
    status = "✅" if result["ok"] else "❌"
    lines  = [f"{status} {step} (código {result['returncode']})"]
    if result["stdout"]:
        lines.append(result["stdout"][-1500:])
    if result["stderr"] and not result["ok"]:
        lines.append(f"STDERR: {result['stderr'][-500:]}")
    return "\n".join(lines)


def _start_preview_background(json_path: Path, cli_cmd: str, port: int) -> str:
    """Inicia servidor de preview em background, matando qualquer processo anterior na porta."""
    import signal
    try:
        pids_out = subprocess.run(
            ["lsof", "-ti", f":{port}"], capture_output=True, text=True
        ).stdout.strip()
        if pids_out:
            for pid in pids_out.split():
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except (ProcessLookupError, ValueError):
                    pass
    except Exception:
        pass
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_REPO_DIR / "src")
    env["PIPELINE_ROOT"] = str(_REPO_DIR)
    subprocess.Popen(
        [_PYTHON, "-m", _PKG, cli_cmd, str(json_path)],
        env=env,
        cwd=str(_REPO_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return f"http://localhost:{port}"


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_workspaces() -> str:
    """Lista todos os workspaces existentes e o estado de cada um.

    Mostra: stage do pipeline, prova.md, questões extraídas/aprovadas/final, upload.
    """
    if not _WORKSPACE_DIR.exists():
        return "Diretório workspace não encontrado."

    workspaces = sorted(
        [d for d in _WORKSPACE_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )
    if not workspaces:
        return "Nenhum workspace encontrado."

    lines = [f"{'Workspace':<40} {'Stage':<14} {'MD':>4} {'Raw':>5} {'Apr':>5} {'Fin':>5} {'UP':>4}"]
    lines.append("-" * 78)
    for ws_dir in workspaces:
        s = _workspace_state(ws_dir)
        ws_st = WorkspaceStage(ws_dir)
        lines.append(
            f"{s['nome']:<40} "
            f"{ws_st.stage:<14} "
            f"{'✅' if s['prova_md'] else '❌':>4} "
            f"{str(s['questoes_raw'] or '-'):>5} "
            f"{str(s['questoes_aprovadas'] or '-'):>5} "
            f"{str(s['questoes_final'] or '-'):>5} "
            f"{'✅' if s['upload_done'] else '❌':>4}"
        )
    lines.append("")
    lines.append("Stage=estado pipeline | MD=prova.md | Raw=extraídas | Apr=aprovadas | Fin=final | UP=Supabase")
    return "\n".join(lines)


@mcp.tool()
def workspace_status(workspace: str) -> str:
    """Estado detalhado de um workspace + próxima acção sugerida.

    Entry-point principal de inspecção — usar sempre que em dúvida sobre o estado.

    Args:
        workspace: Nome do workspace (ex: "EX-MatA635-F1-2024_net")
    """
    ws_dir = _workspace_path(workspace)
    if not ws_dir.exists():
        return f"Workspace '{workspace}' não encontrado."

    s = _workspace_state(ws_dir)
    ws = WorkspaceStage(ws_dir)
    rev = _count_reviewed(workspace)
    reviewed_str = f"{rev[0]}/{rev[1]} revistos" if rev else "—"

    lines = [
        f"Workspace: {s['nome']}",
        f"  estado pipeline:     {ws.stage}",
        f"  prova.md:            {'✅' if s['prova_md'] else '❌ (MinerU pendente)'}",
        f"  questoes_raw.json:   {s['questoes_raw'] or '❌'} questões   [{reviewed_str}]",
        f"  questoes_aprovadas:  {s['questoes_aprovadas'] or '❌'} questões",
        f"  questoes_com_erro:   {s['questoes_com_erro'] or 0} erros",
        f"  questoes_final.json: {s['questoes_final'] or '❌'} questões",
    ]

    # CC workspace associado
    cc_ws_name = _find_cc_workspace(workspace)
    if cc_ws_name:
        cc_dir = _workspace_path(cc_ws_name)
        cc_ws_state = WorkspaceStage(cc_dir)
        cc_data = _workspace_state(cc_dir)
        lines.append(f"  CC workspace:        {cc_ws_name}  (estado CC: {cc_ws_state.cc_stage})")
        if cc_data["criterios_aprovados"]:
            lines.append(f"    criterios_aprovados: {cc_data['criterios_aprovados']} itens")
    else:
        lines.append(f"  CC workspace:        não detectado")

    lines.append(f"  upload Supabase:     {'✅ feito' if s['upload_done'] else '❌ pendente'}")

    # Ficheiros adicionais
    ws_files = sorted(ws_dir.iterdir())
    outros = [f.name for f in ws_files if f.suffix in (".json", ".md", ".html") and f.name not in {
        "prova.md", "questoes_raw.json", "questoes_aprovadas.json",
        "questoes_com_erro.json", "questoes_final.json",
        "criterios_raw.json", "criterios_aprovados.json", "criterios_com_erro.json",
    }]
    if outros:
        lines.append(f"  outros ficheiros:    {', '.join(outros)}")

    lines.append("")
    lines.append(f"Próxima acção: {_next_action(ws_dir, workspace)}")
    return "\n".join(lines)


@mcp.tool()
def run_stage(
    workspace: str,
    stage: str,
    pdf_path: str | None = None,
    workspace_cc: str | None = None,
    force: bool = False,
) -> str:
    """Executa um estágio do pipeline de exames.

    Stages disponíveis:
      extract  — OCR + cotações + estruturação; pdf_path obrigatório se prova.md não existir.
                 Se prova.md já existir (MinerU manual), re-estrutura sem re-correr OCR.
      validate — micro-lint interno + validação heurística. Requer todos os itens reviewed:true.
      cc       — critérios CC-VD: 1ª chamada → cc_extract; 2ª chamada (pós-revisão) → cc_validate.
      merge    — cc_merge + abre preview para revisão humana. Bloqueia se questões sem categorização.
      upload   — upload Supabase + backup automático. Bloqueia sem .review_approved.

    Args:
        workspace:    Nome do workspace da prova (ex: "EX-MatA635-F1-2024_net")
        stage:        Um de: extract | validate | cc | merge | upload
        pdf_path:     Caminho absoluto para o PDF (obrigatório em 'extract' se prova.md não existir)
        workspace_cc: Nome do workspace CC-VD (obrigatório em 'cc' e 'merge'; auto-detectado se omitido)
        force:        Ignora a protecção de estado (DESTRUTIVO — usar com cuidado)
    """
    stage = stage.strip().lower()
    valid_stages = {"extract", "validate", "cc", "merge", "upload"}
    if stage not in valid_stages:
        return (
            f"❌ Stage '{stage}' inválido.\n"
            f"Valores aceites: {', '.join(sorted(valid_stages))}"
        )

    ws_dir = _workspace_path(workspace)
    ws = WorkspaceStage(ws_dir)

    # ── extract ───────────────────────────────────────────────────────────────
    if stage == "extract":
        if not force and (err := ws.require_not_beyond("fresh")):
            return err + "\n\nPara recomeçar use force=True (DESTRUTIVO — apaga trabalho manual)."

        prova_md = ws_dir / "prova.md"

        if pdf_path:
            # Caminho normal: MinerU + cotações + estruturação
            args = ["extract", pdf_path, "--workspace", workspace]
            result = _run(args)
        elif prova_md.exists():
            # MinerU já foi corrido manualmente — só estruturar
            args = ["structure", str(prova_md)]
            result = _run(args)
        else:
            return (
                f"❌ Nenhum PDF nem prova.md encontrado para '{workspace}'.\n\n"
                f"Opção A: run_stage(workspace='{workspace}', stage='extract', pdf_path='<CAMINHO>')\n"
                f"Opção B: correr MinerU no Terminal, copiar prova.md para workspace/{workspace}/, "
                f"depois run_stage(workspace='{workspace}', stage='extract') sem pdf_path."
            )

        if result["ok"]:
            ws.transition("extracted")
            return _format_result("extract", result) + (
                f"\n\n📋 Próximos passos:\n"
                f"  1. Verificar cotacoes_estrutura.json (chaves devem usar prefixo: 'I-1', 'II-2.1')\n"
                f"  2. Rever questoes_raw.json: reviewed:true + categorização em cada item\n"
                f"  3. run_stage(workspace='{workspace}', stage='validate')"
            )
        return _format_result("extract", result)

    # ── validate ──────────────────────────────────────────────────────────────
    if stage == "validate":
        raw = ws_dir / "questoes_raw.json"
        if not raw.exists():
            return (
                f"❌ questoes_raw.json não encontrado em '{workspace}'.\n"
                f"Corre run_stage(workspace='{workspace}', stage='extract') primeiro."
            )

        if not force and (err := ws.require_not_beyond("validated")):
            return err

        # Verificar se todos os itens estão revistos
        rev = _count_reviewed(workspace)
        if rev and not force:
            reviewed, total = rev
            if reviewed < total:
                return (
                    f"❌ {total - reviewed} item(ns) ainda com reviewed:false "
                    f"({reviewed}/{total} revistos).\n"
                    f"Rever todos os itens em questoes_raw.json (Read + Edit) antes de validar."
                )

        # Passo 1 (interno): micro-lint
        lint_result = _run(["micro-lint", str(raw)])
        lint_ok = "✅" if lint_result["ok"] else "❌"
        lint_summary = lint_result["stdout"][-600:] if lint_result["stdout"] else "(sem output)"

        if not lint_result["ok"]:
            return (
                f"❌ micro-lint falhou — corrigir antes de validar:\n"
                f"{lint_summary}"
            )

        # Passo 2 (interno): validate
        val_result = _run(["validate", str(raw)])
        if val_result["ok"]:
            ws.transition("validated")

        return (
            f"{lint_ok} micro-lint\n{lint_summary}\n\n"
            + _format_result("validate", val_result)
            + (
                f"\n\n📋 Próximo passo: run_stage(workspace='{workspace}', stage='cc', "
                f"workspace_cc='<NOME-CC-VD>') — ou run_review se sem CC-VD"
                if val_result["ok"] else ""
            )
        )

    # ── cc ────────────────────────────────────────────────────────────────────
    if stage == "cc":
        if not workspace_cc:
            workspace_cc = _find_cc_workspace(workspace)
        if not workspace_cc:
            return (
                "❌ workspace_cc não fornecido e não foi detectado automaticamente.\n"
                f"Forneça: run_stage(workspace='{workspace}', stage='cc', workspace_cc='<NOME-CC-VD>')"
            )

        ws_cc_dir = _workspace_path(workspace_cc)
        prova_cc_md = ws_cc_dir / "prova.md"

        if not prova_cc_md.exists():
            return (
                f"❌ prova.md não encontrado em '{workspace_cc}'.\n\n"
                f"Correr MinerU no PDF CC-VD (fora do sandbox):\n"
                f"  .venv-mineru/bin/mineru -b pipeline -p '<CC-VD.pdf>' -o workspace/{workspace_cc}\n"
                f"  Copiar prova.md gerado para workspace/{workspace_cc}/prova.md\n"
                f"Depois chamar run_stage(stage='cc', workspace_cc='{workspace_cc}') novamente."
            )

        ws_cc = WorkspaceStage(ws_cc_dir)
        cc_st = ws_cc.cc_stage

        if cc_st == "cc_validated":
            return (
                f"✅ CC-VD já validado (estado: {cc_st}).\n"
                f"Próximo passo: run_stage(workspace='{workspace}', stage='merge', workspace_cc='{workspace_cc}')"
            )

        if cc_st == "cc_fresh":
            # 1ª chamada: extrair critérios
            result = _run(["cc-extract", str(prova_cc_md)])
            if result["ok"]:
                ws_cc.transition_cc("cc_extracted")
                return _format_result("cc-extract", result) + (
                    f"\n\n📋 Próximos passos:\n"
                    f"  1. Rever criterios_raw.json em '{workspace_cc}':\n"
                    f"     • Setar reviewed:true em cada item\n"
                    f"     • GRUPO I (MC): preencher resposta_correta (gabarito na imagem do PDF)\n"
                    f"     • Itens abertos sem etapas: extrair do bloco_ocr ou PDF com Edit\n"
                    f"     • Duplicados 'II-*': apagar entradas prefixadas se existirem versões simples\n"
                    f"  2. run_stage(workspace='{workspace}', stage='cc', workspace_cc='{workspace_cc}')"
                )
            return _format_result("cc-extract", result)

        # cc_extracted: 2ª chamada (pós-revisão) → validar
        raw_cc = ws_cc_dir / "criterios_raw.json"
        if not raw_cc.exists():
            return f"❌ criterios_raw.json não encontrado em '{workspace_cc}'."

        result = _run(["cc-validate", str(raw_cc)])
        if result["ok"]:
            ws_cc.transition_cc("cc_validated")
            return _format_result("cc-validate", result) + (
                f"\n\n📋 Próximo passo: run_stage(workspace='{workspace}', stage='merge', workspace_cc='{workspace_cc}')"
            )
        return _format_result("cc-validate", result)

    # ── merge ─────────────────────────────────────────────────────────────────
    if stage == "merge":
        if not workspace_cc:
            workspace_cc = _find_cc_workspace(workspace)
        if not workspace_cc:
            return (
                "❌ workspace_cc não fornecido e não detectado automaticamente.\n"
                f"Forneça: run_stage(workspace='{workspace}', stage='merge', workspace_cc='<NOME-CC-VD>')"
            )

        ws_cc_dir = _workspace_path(workspace_cc)
        approved = ws_dir / "questoes_aprovadas.json"
        criterios = ws_cc_dir / "criterios_aprovados.json"

        if not approved.exists():
            return f"❌ questoes_aprovadas.json não encontrado em '{workspace}'."
        if not criterios.exists():
            return f"❌ criterios_aprovados.json não encontrado em '{workspace_cc}'. Corre run_stage(stage='cc') primeiro."

        if not force:
            if ws.stage == "cc_merged":
                return (
                    f"ℹ️  Merge já concluído (estado: cc_merged).\n"
                    f"Próximo passo: run_review(workspace='{workspace}')"
                )
            if err := ws.require_exactly("validated"):
                return err

        ws_cc = WorkspaceStage(ws_cc_dir)
        if err := ws_cc.require_cc_at_least("cc_validated"):
            return err

        # Gate obrigatório: categorização completa
        uncategorized = check_all_categorized(approved)
        if uncategorized:
            items_list = "\n".join(f"  • {id_}" for id_ in uncategorized)
            return (
                f"❌ BLOQUEADO: {len(uncategorized)} questão(ões) sem categorização em '{workspace}'.\n"
                f"Preencher tema, subtema, descricao_breve e tags antes do merge:\n"
                f"{items_list}\n\n"
                f"Editar directamente em questoes_aprovadas.json com Read + Edit."
            )

        result = _run(["cc-merge", str(criterios), str(approved)])
        output = _format_result("cc-merge", result)

        if result["ok"]:
            ws.transition("cc_merged")
            final = ws_dir / "questoes_final.json"
            if final.exists():
                # Apagar aprovação anterior — novo merge exige nova revisão humana
                review_flag = ws_dir / ".review_approved"
                if review_flag.exists():
                    review_flag.unlink()
                    ws.reset_to("cc_merged")
                url = _start_preview_background(final, "preview", 8798)
                output += (
                    f"\n\n⚠️  REVISÃO HUMANA OBRIGATÓRIA antes do upload!\n"
                    f"🔍 Preview: {url}\n"
                    f"   Clique '✅ Aprovar para Upload' quando estiver satisfeito.\n"
                    f"   Depois: run_stage(workspace='{workspace}', stage='upload')"
                )
        return output

    # ── upload ────────────────────────────────────────────────────────────────
    if stage == "upload":
        final = ws_dir / "questoes_final.json"
        if not final.exists():
            approved = ws_dir / "questoes_aprovadas.json"
            if approved.exists():
                final = approved
            else:
                return (
                    f"❌ questoes_final.json não encontrado em '{workspace}'.\n"
                    f"Corre run_stage(stage='merge') primeiro."
                )

        if not force and (err := ws.require_exactly("human_approved")):
            return (
                f"❌ Upload bloqueado: revisão humana obrigatória.\n"
                f"Estado actual: '{ws.stage}'\n\n"
                f"Passos:\n"
                f"  1. run_review(workspace='{workspace}') para abrir o preview\n"
                f"  2. Revise todas as questões\n"
                f"  3. Clique '✅ Aprovar para Upload' no preview\n"
                f"  4. run_stage(workspace='{workspace}', stage='upload') novamente"
            )

        result = _run(["upload", str(final)])

        if result["ok"]:
            (ws_dir / ".upload_done").touch()
            ws.transition("uploaded")
            # Backup automático após upload
            backup_result = _run(["backup"])
            backup_msg = (
                "\n✅ Backup automático concluído."
                if backup_result["ok"]
                else f"\n⚠️  Backup automático falhou: {backup_result['stderr'][:200]}"
            )
            return _format_result("upload", result) + backup_msg

        return _format_result("upload", result)


@mcp.tool()
def run_review(workspace: str) -> str:
    """Abre o preview interactivo de questoes_final.json para revisão humana.

    Obrigatório entre run_stage('merge') e run_stage('upload').
    O utilizador revê as questões e clica '✅ Aprovar para Upload' para desbloquear o upload.

    Args:
        workspace: Nome do workspace com questoes_final.json
    """
    final = _workspace_path(workspace) / "questoes_final.json"
    if not final.exists():
        approved = _workspace_path(workspace) / "questoes_aprovadas.json"
        if approved.exists():
            final = approved
        else:
            return (
                f"❌ questoes_final.json não encontrado em '{workspace}'.\n"
                f"Corre run_stage(stage='merge') primeiro."
            )

    url = _start_preview_background(final, "preview", 8798)
    review_flag = _workspace_path(workspace) / ".review_approved"
    status = "✅ Já aprovado" if review_flag.exists() else "⏳ Aguarda aprovação humana"

    return (
        f"🔍 Preview: {url}\n"
        f"   Estado: {status}\n\n"
        f"Instruções:\n"
        f"  1. Revise todas as questões e critérios\n"
        f"  2. Use os botões ✏️ para editar inline qualquer campo\n"
        f"  3. Clique '✅ Aprovar para Upload' na barra inferior quando satisfeito\n"
        f"  4. Depois: run_stage(workspace='{workspace}', stage='upload')\n\n"
        f"Para correcções pontuais: run_fix_question(workspace, id_item, field, value)"
    )


@mcp.tool()
def run_fix_question(
    workspace: str,
    id_item: str,
    field: str,
    value: str,
) -> str:
    """Corrige um campo específico de uma questão em questoes_final.json (não-destrutivo).

    NUNCA corre validate, extract ou outros módulos — edita apenas o campo indicado.
    Apaga a aprovação humana (.review_approved) — nova revisão é necessária antes do upload.

    Campos permitidos: enunciado, solucao, resposta_correta, descricao_breve,
                       tema, subtema, tags (JSON array), observacoes (JSON array)

    Args:
        workspace: Nome do workspace
        id_item:   ID do item a corrigir (ex: "II-3.2", "I-5")
        field:     Campo a alterar
        value:     Novo valor (para 'tags'/'observacoes' passar JSON array como string)
    """
    import json as _json

    ws_dir = _workspace_path(workspace)
    ws = WorkspaceStage(ws_dir)
    if err := ws.require_at_least("validated"):
        return err

    final = ws_dir / "questoes_final.json"
    if not final.exists():
        return f"❌ questoes_final.json não encontrado em '{workspace}'."

    ALLOWED = {"enunciado", "solucao", "resposta_correta", "descricao_breve",
               "tema", "subtema", "tags", "observacoes"}
    if field not in ALLOWED:
        return (
            f"❌ Campo '{field}' não permitido.\n"
            f"Campos editáveis: {', '.join(sorted(ALLOWED))}"
        )

    try:
        data = _json.loads(final.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"❌ Erro ao ler questoes_final.json: {exc}"

    found = False
    for q in data:
        if str(q.get("id_item", "")) == id_item:
            if field in ("tags", "observacoes"):
                try:
                    q[field] = _json.loads(value)
                except _json.JSONDecodeError:
                    return f"❌ Valor inválido para '{field}': deve ser JSON array (ex: [\"tag1\",\"tag2\"])"
            else:
                q[field] = value
            found = True
            break

    if not found:
        ids = [str(q.get("id_item", "")) for q in data]
        return f"❌ Item '{id_item}' não encontrado. IDs disponíveis: {ids}"

    try:
        final.write_text(_json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        return f"❌ Erro ao gravar: {exc}"

    # Apagar aprovação — nova correcção requer nova revisão humana
    review_flag = ws_dir / ".review_approved"
    if review_flag.exists():
        review_flag.unlink()
        has_final = (ws_dir / "questoes_final.json").exists()
        ws.reset_to("cc_merged" if has_final else "validated")
        needs_reapproval = "\n⚠️  Aprovação resetada — revise e aprove novamente antes do upload."
    else:
        needs_reapproval = ""

    return (
        f"✅ {id_item}.{field} actualizado em questoes_final.json.{needs_reapproval}\n"
        f"Use run_review(workspace='{workspace}') para verificar e aprovar."
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
