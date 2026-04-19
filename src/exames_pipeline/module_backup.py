"""Módulo de backup local do Supabase.

Dois tipos de backup:

1. backup_workspace_files(workspace_dir, backup_root)  — pré-upload
   Copia os ficheiros de trabalho do workspace para backup/workspaces/<nome>/.
   Instantâneo; preserva o estado antes de qualquer alteração remota.

2. run_backup(settings, backup_root)  — pós-upload
   Descarrega apenas os 5 JSONs das tabelas do Supabase (captura os IDs gerados).
   Tabelas descarregadas em paralelo. Sem download de imagens — já existem
   localmente em workspace/*/images/.

Estrutura de saída:
    backup/
      workspaces/
        <workspace>/          ← cópia pré-upload dos ficheiros de trabalho
          questoes_final.json
          prova.md
          questoes_review.json
          criterios_raw.json
          ...
      supabase/               ← snapshot pós-upload das tabelas do Supabase
        materias.json
        fontes.json
        topicos.json
        contextos.json
        questoes.json
        backup_meta.json      ← timestamp, contagens, versão do schema
"""
from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings


_TABLES = ["materias", "fontes", "topicos", "contextos", "questoes"]
_PAGE_SIZE = 1000       # linhas por página (máx Supabase REST)
_TABLE_WORKERS = 5      # threads para fetch de tabelas (uma por tabela)

# Ficheiros de trabalho a copiar no backup pré-upload
_WORKSPACE_FILES = [
    "questoes_final.json",
    "questoes_review.json",
    "questoes_meta.json",
    "questoes_final.materialized.json",
    "criterios_raw.json",
    "cotacoes_estrutura.json",
    "prova.md",
    "state.json",
]

# Lock para prints concorrentes não se misturarem
_print_lock = threading.Lock()


def _safe_print(msg: str) -> None:
    with _print_lock:
        print(msg)


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _sb_headers(settings: Settings) -> dict[str, str]:
    return {
        "apikey":        settings.supabase_key,
        "Authorization": f"Bearer {settings.supabase_key}",
    }


def _get_bytes(url: str, headers: dict[str, str]) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


# ── Backup de workspace (pré-upload) ─────────────────────────────────────────

def backup_workspace_files(
    workspace_dir: Path,
    backup_root: Path | None = None,
) -> Path:
    """Copia os ficheiros de trabalho do workspace para backup/workspaces/<nome>/.

    Deve ser chamado ANTES do upload. Preserva o estado local dos ficheiros
    antes de qualquer alteração remota.

    Args:
        workspace_dir: Caminho do workspace (ex: .../workspace/EX-MatA635-EE-2023).
        backup_root:   Raiz do backup (default: <project_root>/backup).

    Returns:
        Caminho do directório de destino.
    """
    project_root = workspace_dir.parent.parent
    dest_root = backup_root or (project_root / "backup")
    dest = dest_root / "workspaces" / workspace_dir.name
    dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    for fname in _WORKSPACE_FILES:
        src = workspace_dir / fname
        if src.exists():
            shutil.copy2(src, dest / fname)
            copied += 1

    print(f"[backup] 📁 Workspace '{workspace_dir.name}': {copied} ficheiros → {dest}")
    return dest


# ── Tabelas ───────────────────────────────────────────────────────────────────

def _fetch_table(settings: Settings, headers: dict[str, str], table: str) -> list[dict]:
    """Descarrega todos os registos de uma tabela paginando de PAGE_SIZE em PAGE_SIZE."""
    rows: list[dict] = []
    offset = 0
    while True:
        url = (
            f"{settings.supabase_url}/rest/v1/{table}"
            f"?select=*&order=id&limit={_PAGE_SIZE}&offset={offset}"
        )
        hdrs = {**headers, "Prefer": "count=exact"}
        req = urllib.request.Request(url, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                batch = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Erro ao ler tabela {table}: HTTP {exc.code} — {body[:200]}") from exc
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return rows


def _fetch_and_save_table(
    settings: Settings,
    headers: dict[str, str],
    table: str,
    backup_dir: Path,
) -> dict[str, Any]:
    """Wrapper para fetch + save de uma tabela; retorna entry de meta."""
    _safe_print(f"[backup] A descarregar tabela: {table}…")
    try:
        rows = _fetch_table(settings, headers, table)
        out = backup_dir / f"{table}.json"
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        _safe_print(f"[backup]   ✅ {table}: {len(rows)} registos → {out.name}")
        return {"count": len(rows), "file": f"{table}.json"}
    except Exception as exc:
        _safe_print(f"[backup]   ❌ {table}: {exc}")
        return {"error": str(exc)}


# ── Backup das tabelas Supabase (pós-upload) ──────────────────────────────────

def run_backup(settings: Settings, backup_root: Path | None = None) -> Path:
    """Descarrega as tabelas do Supabase para o disco local (pós-upload).

    Captura os IDs gerados pelo Supabase após o upload. Não baixa imagens —
    essas já existem localmente em workspace/*/images/.

    As tabelas são descarregadas em paralelo.

    Args:
        settings:    Configurações do pipeline.
        backup_root: Directório raiz do backup (default: <project_root>/backup/supabase).

    Returns:
        Caminho para backup_meta.json.
    """
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY não configurados.")

    backup_dir = backup_root or (settings.project_root / "backup" / "supabase")
    backup_dir.mkdir(parents=True, exist_ok=True)

    headers = _sb_headers(settings)
    started_at = datetime.now(timezone.utc)
    meta: dict[str, Any] = {
        "schema_version": "v2",
        "started_at": started_at.isoformat(),
        "tables": {},
    }

    # Tabelas em paralelo
    with ThreadPoolExecutor(max_workers=_TABLE_WORKERS) as pool:
        futs = {
            pool.submit(_fetch_and_save_table, settings, headers, t, backup_dir): t
            for t in _TABLES
        }
        for fut in as_completed(futs):
            table = futs[fut]
            try:
                meta["tables"][table] = fut.result()
            except Exception as exc:
                meta["tables"][table] = {"error": str(exc)}

    meta["finished_at"] = datetime.now(timezone.utc).isoformat()
    meta_path = backup_dir / "backup_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[backup] 🎉 Tabelas do Supabase guardadas → {backup_dir}")
    return meta_path
