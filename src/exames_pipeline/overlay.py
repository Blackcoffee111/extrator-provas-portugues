"""Overlay de correcções humanas/agente sobre questoes_final.json.

Ficheiro mantido em: workspace/<ws>/correcoes_humanas.json

Formato:
{
  "version": 1,
  "updated_at": "2026-04-14T10:22:00Z",
  "items": {
    "II-3.2": {
      "enunciado":  {"value": "...", "ts": "...", "source": "human"},
      "tags":       {"value": ["a","b"], "ts": "...", "source": "agent"}
    }
  }
}

Política: override SEMPRE vence. Sem resolução de conflito.
Campos suportados: enunciado, enunciado_contexto_pai, solucao, resposta_correta,
                   alternativas, criterios_parciais, resolucoes_alternativas,
                   descricao_breve, tema, subtema, tags, observacoes.
Campos estruturais (id_item, tipo_item) não passam pelo overlay.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FILENAME = "correcoes_humanas.json"


# ── I/O ───────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _overlay_path(ws_dir: Path) -> Path:
    return ws_dir / _FILENAME


def load_overlay(ws_dir: Path) -> dict:
    """Carrega o overlay ou devolve estrutura vazia."""
    path = _overlay_path(ws_dir)
    if not path.exists():
        return {"version": 1, "updated_at": _now(), "items": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data.get("items"), dict):
            data["items"] = {}
        return data
    except Exception:
        return {"version": 1, "updated_at": _now(), "items": {}}


def _save_overlay(ws_dir: Path, overlay: dict) -> None:
    path = _overlay_path(ws_dir)
    path.write_text(json.dumps(overlay, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Escrita ───────────────────────────────────────────────────────────────────

def set_override(
    ws_dir: Path,
    id_item: str,
    field: str,
    value: Any,
    source: str = "agent",
) -> None:
    """Grava (ou actualiza) um override para um campo de um item."""
    overlay = load_overlay(ws_dir)
    items = overlay.setdefault("items", {})
    item_overrides = items.setdefault(id_item, {})
    item_overrides[field] = {
        "value": value,
        "ts": _now(),
        "source": source,
    }
    overlay["updated_at"] = _now()
    _save_overlay(ws_dir, overlay)


def clear_override(ws_dir: Path, id_item: str, field: str | None = None) -> None:
    """Remove um override pontual ou todos os overrides de um item."""
    overlay = load_overlay(ws_dir)
    items = overlay.get("items", {})
    if id_item not in items:
        return
    if field is None:
        del items[id_item]
    else:
        items[id_item].pop(field, None)
        if not items[id_item]:
            del items[id_item]
    overlay["updated_at"] = _now()
    _save_overlay(ws_dir, overlay)


# ── Aplicação ─────────────────────────────────────────────────────────────────

def apply_overlay(
    base_list: list[dict],
    overlay: dict,
) -> tuple[list[dict], list[str]]:
    """Aplica o overlay sobre a lista base.

    Devolve (merged, orphan_ids):
    - merged:     lista com overrides aplicados (cópia — não modifica base)
    - orphan_ids: ids do overlay que não existem na base (logados, não apagados)
    """
    items = overlay.get("items", {})
    base_ids = {str(q.get("id_item", "")) for q in base_list}
    orphans  = [id_ for id_ in items if id_ not in base_ids]

    merged = []
    for q in base_list:
        item_id = str(q.get("id_item", ""))
        q_copy  = copy.deepcopy(q)
        if item_id in items:
            for field, override in items[item_id].items():
                q_copy[field] = override["value"]
        merged.append(q_copy)

    return merged, orphans


def get_item_overrides(overlay: dict, id_item: str) -> dict[str, str]:
    """Devolve {field: source} para um item (para exibição de badges)."""
    item = overlay.get("items", {}).get(id_item, {})
    return {field: entry["source"] for field, entry in item.items()}


# ── Materialização ────────────────────────────────────────────────────────────

def materialize(ws_dir: Path, base_path: Path | None = None) -> tuple[Path, list[str]]:
    """Aplica overlay sobre questoes_final.json → questoes_final.materialized.json.

    Tenta questoes_final.json primeiro; cai em questoes_aprovadas.json.
    Devolve (path_do_materialized, orphan_ids).
    """
    if base_path is None:
        base_path = ws_dir / "questoes_final.json"
        if not base_path.exists():
            base_path = ws_dir / "questoes_aprovadas.json"

    overlay  = load_overlay(ws_dir)
    base     = json.loads(base_path.read_text(encoding="utf-8"))
    merged, orphans = apply_overlay(base, overlay)

    out_path = ws_dir / "questoes_final.materialized.json"
    out_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path, orphans


def canonical_hash(data: list) -> str:
    """Hash SHA-256 canónico da lista (para comparar snapshots)."""
    import hashlib
    normalized = sorted(copy.deepcopy(data), key=lambda q: q.get("id_item", ""))
    canonical  = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Resumo ────────────────────────────────────────────────────────────────────

def overlay_summary(ws_dir: Path) -> dict:
    """Devolve {has_overlay, items, fields, orphans}."""
    overlay = load_overlay(ws_dir)
    items   = overlay.get("items", {})
    if not items:
        return {"has_overlay": False, "items": 0, "fields": 0, "orphans": 0}

    base_path = ws_dir / "questoes_final.json"
    if not base_path.exists():
        base_path = ws_dir / "questoes_aprovadas.json"

    orphans = 0
    if base_path.exists():
        try:
            base     = json.loads(base_path.read_text(encoding="utf-8"))
            base_ids = {str(q.get("id_item", "")) for q in base}
            orphans  = sum(1 for id_ in items if id_ not in base_ids)
        except Exception:
            pass

    total_fields = sum(len(v) for v in items.values())
    return {
        "has_overlay": True,
        "items":       len(items),
        "fields":      total_fields,
        "orphans":     orphans,
    }


# ── Helpers para o handler do preview ─────────────────────────────────────────

def get_effective_field(
    base_list: list[dict],
    overlay: dict,
    id_item: str,
    field: str,
    default: Any = None,
) -> Any:
    """Devolve o valor efectivo (overlay > base) de um campo de um item."""
    item_overrides = overlay.get("items", {}).get(id_item, {})
    if field in item_overrides:
        return item_overrides[field]["value"]
    for q in base_list:
        if str(q.get("id_item", "")) == id_item:
            return q.get(field, default)
    return default
