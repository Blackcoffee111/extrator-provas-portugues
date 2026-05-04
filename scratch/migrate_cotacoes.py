"""Migra cotacoes_estrutura.json legados para o formato canónico.

Formatos aceites na entrada:
  A. `{"I-1": 13, "I-2": 13, ...}` (plano)
  B. `{"I-1": 13.0, ...}` (plano com floats)
  C. `{"I-A-1": {"tipo": "", "pontos": null}, ...}` (stub vazio)
  D. `{"cotacoes": {...}}` (canónico — re-normaliza pool_opcional)
  E. `{... "pool_opcional": {"pontos": 39, "itens":[...], "escolher": 3}}` (legado:
     pool como dict no topo, em vez de lista)

Saída: formato canónico com chaves
  cotacoes, estrutura, total_itens_principais, confianca, pool_opcional, raw_response.

Uso:
  python scratch/migrate_cotacoes.py            # migra todos os workspaces
  python scratch/migrate_cotacoes.py <path>     # migra um ficheiro específico
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _build_estrutura(cotacoes: dict[str, int]) -> dict[str, list[str]]:
    estrutura: dict[str, list[str]] = {}
    for item_id in cotacoes:
        numeric_part = item_id.split("-")[-1]
        if "." in numeric_part:
            parent_id = item_id.rsplit(".", 1)[0]
            estrutura.setdefault(parent_id, [])
            if item_id not in estrutura[parent_id]:
                estrutura[parent_id].append(item_id)
        else:
            estrutura.setdefault(item_id, [])
    return estrutura


def _normalize_pool(raw: object) -> list[dict]:
    """Normaliza pool_opcional para lista de {pontos, itens, escolher}."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        # Formato legado: dict único no topo
        return [{
            "pontos": raw.get("pontos"),
            "itens": list(raw.get("itens", [])),
            "escolher": int(raw.get("escolher", 0)),
        }]
    if isinstance(raw, list):
        return [
            {
                "pontos": entry.get("pontos"),
                "itens": list(entry.get("itens", [])),
                "escolher": int(entry.get("escolher", 0)),
            }
            for entry in raw
            if isinstance(entry, dict)
        ]
    return []


def migrate(raw: dict) -> dict:
    """Converte qualquer formato suportado para o canónico."""
    pool_opcional_raw = raw.pop("pool_opcional", None) if isinstance(raw, dict) else None

    if "cotacoes" in raw:
        # Já canónico — re-normalizar
        cotacoes = {str(k): int(round(float(v))) for k, v in raw["cotacoes"].items()}
        confianca = raw.get("confianca", "alta")
        raw_response = raw.get("raw_response", "")
        bypass_validation = bool(raw.get("bypass_validation", False))
        bypass_motivo = str(raw.get("bypass_motivo", ""))
        pool_opcional = _normalize_pool(pool_opcional_raw or raw.get("pool_opcional"))
        # Garantir que itens declarados em pool aparecem também no manifesto.
        for pool in pool_opcional:
            pool_pts_total = pool.get("pontos")
            per_item = (
                int(round(pool_pts_total / pool["escolher"]))
                if pool_pts_total and pool.get("escolher")
                else 13
            )
            for item_id in pool.get("itens", []):
                if item_id not in cotacoes:
                    cotacoes[item_id] = per_item
        estrutura = raw.get("estrutura") or _build_estrutura(cotacoes)
        estrutura = {str(k): list(v) for k, v in estrutura.items()}
        # Garantir que itens novos do pool entram na estrutura
        for item_id in cotacoes:
            numeric_part = item_id.split("-")[-1]
            if "." not in numeric_part:
                estrutura.setdefault(item_id, [])
        total = sum(1 for k in estrutura if "." not in k.split("-")[-1])
    else:
        # Formatos planos / stub
        cotacoes = {}
        for k, v in raw.items():
            if isinstance(v, (int, float)):
                cotacoes[str(k)] = int(round(float(v)))
            elif isinstance(v, dict):
                pts = v.get("pontos")
                if isinstance(pts, (int, float)):
                    cotacoes[str(k)] = int(round(float(pts)))
                else:
                    # Stub: assumir 13 (uniform PT) — caller pode ajustar manualmente
                    cotacoes[str(k)] = 13 if not str(k).startswith("III") else 44
        confianca = "alta"
        raw_response = ""
        bypass_validation = False
        bypass_motivo = ""
        pool_opcional = _normalize_pool(pool_opcional_raw)
        # Itens declarados em pools mas ausentes no mapa plano: incluí-los no
        # manifesto canónico (são itens reais do exame; o pool só restringe
        # quais contam para a nota).
        for pool in pool_opcional:
            pool_pts_total = pool.get("pontos")
            pool_itens = pool.get("itens", [])
            per_item = (
                int(round(pool_pts_total / pool["escolher"]))
                if pool_pts_total and pool.get("escolher")
                else 13
            )
            for item_id in pool_itens:
                if item_id not in cotacoes:
                    cotacoes[item_id] = per_item
        estrutura = _build_estrutura(cotacoes)
        total = sum(1 for k in estrutura if "." not in k.split("-")[-1])

    return {
        "total_itens_principais": total,
        "estrutura": estrutura,
        "cotacoes": cotacoes,
        "confianca": confianca,
        "raw_response": raw_response,
        "pool_opcional": pool_opcional,
        "bypass_validation": bypass_validation,
        "bypass_motivo": bypass_motivo,
    }


def migrate_file(path: Path) -> bool:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        print(f"[skip] {path}: raiz não é objecto JSON")
        return False
    canonical = migrate(raw)
    path.write_text(
        json.dumps(canonical, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[ok]   {path}: {len(canonical['cotacoes'])} itens, "
          f"{len(canonical['pool_opcional'])} pool(s)")
    return True


def main() -> int:
    if len(sys.argv) > 1:
        targets = [Path(p) for p in sys.argv[1:]]
    else:
        repo = Path(__file__).resolve().parent.parent
        targets = sorted((repo / "workspace").glob("*/cotacoes_estrutura.json"))

    if not targets:
        print("Nenhum ficheiro encontrado.")
        return 1

    for path in targets:
        try:
            migrate_file(path)
        except Exception as exc:
            print(f"[err]  {path}: {exc}")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
