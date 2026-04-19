"""
Módulo CC-Validate — Validação heurística dos critérios extraídos do CC-VD.

Validações aplicadas:
  1. MC com letra inválida — resposta_correta ∉ {A, B, C, D}
  2. Aberta com solução vazia — solucao == "" após extração LLM
  3. Aberta sem etapas — criterios_parciais == [] para item open_response
  4. Tipo desconhecido — tipo não é "multiple_choice" nem "open_response"

Saídas:
  criterios_aprovados.json  — itens que passaram todas as validações (ou apenas warnings)
  criterios_com_erro.json   — itens rejeitados
  criterios_validacao_cc.json — relatório completo
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .schemas import CriterioRaw, dump_criterios, load_criterios, dump_json

_VALID_MC_LETTERS = {"A", "B", "C", "D"}


def _validate_criterio(c: CriterioRaw) -> tuple[list[str], list[str]]:
    """
    Retorna (erros, avisos) para um critério.
    Erros → rejeição; avisos → aprovação com suspeitas.
    """
    erros: list[str] = []
    avisos: list[str] = []

    if c.tipo not in {"multiple_choice", "open_response"}:
        erros.append(f"tipo desconhecido: '{c.tipo}'")
        return erros, avisos

    if not c.reviewed:
        erros.append("critério ainda não foi revisto pelo agente (reviewed: false)")

    if c.tipo == "multiple_choice":
        if not c.resposta_correta or c.resposta_correta.upper() not in _VALID_MC_LETTERS:
            erros.append(
                f"resposta_correta inválida: '{c.resposta_correta}' "
                f"(esperado A, B, C ou D)"
            )

    else:  # open_response
        if not c.solucao or not c.solucao.strip():
            erros.append("solucao vazia após extração LLM")

        if not c.criterios_parciais:
            erros.append("criterios_parciais vazio — nenhuma etapa extraída")
    return erros, avisos


def validate_criterios(raw_path: Path) -> tuple[Path, Path]:
    """
    Valida criterios_raw.json e separa aprovados de rejeitados.

    Retorna (approved_path, rejected_path).
    """
    raw_path = raw_path.resolve()
    output_dir = raw_path.parent
    criterios = load_criterios(raw_path)

    approved: list[CriterioRaw] = []
    rejected: list[CriterioRaw] = []
    report: list[dict] = []

    for c in criterios:
        erros, avisos = _validate_criterio(c)

        if erros:
            c_copy = replace(
                c,
                status="error",
                observacoes=list(c.observacoes) + [f"ERRO: {e}" for e in erros]
                            + [f"AVISO: {a}" for a in avisos],
            )
            rejected.append(c_copy)
            icon = "❌"
        elif avisos:
            c_copy = replace(
                c,
                status="approved_with_warnings",
                observacoes=list(c.observacoes) + [f"AVISO: {a}" for a in avisos],
            )
            approved.append(c_copy)
            icon = "⚠️"
        else:
            c_copy = replace(c, status="approved")
            approved.append(c_copy)
            icon = "✅"

        print(f"[cc_validate] {icon} {c.id_item} ({c.tipo})"
              + (f" — {'; '.join(erros + avisos)}" if erros or avisos else ""))

        report.append({
            "id_item": c.id_item,
            "tipo": c.tipo,
            "status": c_copy.status,
            "erros": erros,
            "avisos": avisos,
        })

    approved_path = output_dir / "criterios_aprovados.json"
    rejected_path = output_dir / "criterios_com_erro.json"
    report_path   = output_dir / "criterios_validacao_cc.json"

    dump_criterios(approved_path, approved)
    dump_criterios(rejected_path, rejected)
    dump_json(report_path, report)

    n_ok  = len(approved)
    n_err = len(rejected)
    print(f"\n[cc_validate] {n_ok} aprovados · {n_err} rejeitados")
    print(f"  ✅ {approved_path}")
    print(f"  ❌ {rejected_path}")
    print(f"  📋 {report_path}")
    return approved_path, rejected_path
