"""
Módulo CC-Validate — Validação heurística dos critérios extraídos do CC-VD.

Validações aplicadas:
  1. MC com letra inválida — resposta_correta ∉ {A, B, C, D}
  2. Aberta com solução vazia — solucao == "" após extração LLM
  3. Aberta sem etapas — criterios_parciais == [] para item open_response
  4. Tipo desconhecido — tipo não é "multiple_choice" nem "open_response"
  5. OCR-SUSPECT sem resolução — observacoes com OCR-SUSPECT: sem OCR-RESOLVED: ou OCR-FALSE-POSITIVE:
  6. Token-diff (aviso) — tokens em descricao/solucao ausentes em texto_original e não documentados

Saídas:
  criterios_aprovados.json    — itens que passaram todas as validações (ou apenas avisos)
  criterios_com_erro.json     — itens rejeitados
  criterios_validacao_cc.json — relatório completo
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

from .schemas import CriterioRaw, dump_criterios, load_criterios, dump_json

_VALID_MC_LETTERS = {"A", "B", "C", "D"}


def _check_ocr_suspects(c: CriterioRaw) -> list[str]:
    """Erro se existir OCR-SUSPECT: sem resolução correspondente.

    Para cada observação "OCR-SUSPECT: <tipo> '<trecho>'" verifica se existe
    pelo menos uma observação "OCR-RESOLVED: ..." ou "OCR-FALSE-POSITIVE: ...".
    Basta UMA resolução/false-positive para libertar TODOS os suspects do item
    — assume que o agente reviu o contexto completo.
    """
    suspects = [o for o in c.observacoes if o.startswith("OCR-SUSPECT:")]
    if not suspects:
        return []
    resolved = any(
        o.startswith("OCR-RESOLVED:") or o.startswith("OCR-FALSE-POSITIVE:")
        for o in c.observacoes
    )
    if resolved:
        return []
    return [
        f"OCR-SUSPECT não resolvido: {len(suspects)} suspeita(s) pendente(s). "
        f"Adicionar 'OCR-RESOLVED: original→correcto' ou 'OCR-FALSE-POSITIVE: justificação' "
        f"nas observacoes após rever o item."
    ]


def _check_token_diff(c: CriterioRaw) -> list[str]:
    """Aviso se campos editáveis contêm tokens não presentes em texto_original.

    Serve para detectar palavras que o agente introduziu sem correspondência no OCR bruto.
    Ignora tokens explicados em notas OCR-RESOLVED / OCR-FALSE-POSITIVE.
    """
    if not c.texto_original:
        return []

    def _tokenize(text: str) -> set[str]:
        return {w.lower() for w in re.findall(r'[a-záàâãéêíóôõúüçA-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ]{5,}', text)}

    original_tokens = _tokenize(c.texto_original)

    # Tokens mencionados em notas de resolução → aceites
    resolution_notes = " ".join(
        o for o in c.observacoes
        if o.startswith("OCR-RESOLVED:") or o.startswith("OCR-FALSE-POSITIVE:")
    )
    resolution_tokens = _tokenize(resolution_notes)

    edited_text = (c.solucao or "")
    for step in c.criterios_parciais:
        edited_text += " " + step.get("descricao", "")
    for alt in c.resolucoes_alternativas:
        edited_text += " " + alt
    edited_tokens = _tokenize(edited_text)

    suspicious = edited_tokens - original_tokens - resolution_tokens
    if not suspicious:
        return []

    sample = sorted(suspicious)[:4]
    suffix = " (e outros)" if len(suspicious) > 4 else ""
    return [
        f"token(s) ausentes em texto_original: {', '.join(sample)}{suffix} "
        f"— se correcção OCR intencional, documentar em 'OCR-RESOLVED: original→correcto'"
    ]


def _mirror_complete_table_solucao(criterios: list[CriterioRaw]) -> int:
    """Espelha `solucao` para o 1.º criterios_parciais em itens complete_table.

    Para complete_table (tab), a `solucao` é a chave de respostas curta
    (ex: "a) 3; b) 1; c) 2"). O 1.º criterios_parciais deve conter APENAS
    essa resposta — sem descritor C-ED, sem texto adicional. Diferente
    de open_response/essay, onde se prepende preservando o descritor.

    Corre no validate (não no extract) porque a solucao do extract é
    block.text bruto; só após o agente a limpar é que vale a pena espelhar.

    Sem efeito quando:
      - tipo != complete_table
      - solucao vazia/whitespace
      - 1.º criterios_parciais já tem descricao == solucao (idempotente)
    """
    n = 0
    for c in criterios:
        if c.tipo != "complete_table":
            continue
        solucao = (c.solucao or "").strip()
        if not solucao:
            continue
        if c.criterios_parciais:
            first = c.criterios_parciais[0]
            if (first.get("descricao") or "").strip() == solucao:
                continue
            first["descricao"] = solucao
            if "pontos" not in first and "nivel" not in first:
                first["pontos"] = c.cotacao_total
        else:
            c.criterios_parciais = [
                {"pontos": c.cotacao_total, "descricao": solucao}
            ]
        n += 1
    return n


def _check_solucao_mirrored(c: CriterioRaw) -> list[str]:
    """Erro se `solucao` substancial não estiver espelhada em criterios_parciais.

    Contrato (AGENTS.md §6b.0.1, .claude/skills/exames.md): para open_response
    e essay, o texto da resolução completa deve aparecer em pelo menos um
    criterios_parciais[].descricao — o preview e o Supabase mostram os dois
    campos por caminhos distintos, e deixar criterios_parciais só com o
    descritor C-ED esconde a resposta esperada do classificador humano.

    Aplica apenas a tipos open_response/essay com solucao não-trivial
    (≥80 chars após strip). MC, complete_table e multi_select têm solucao
    curta tipo "Opção (A)" — espelhar não acrescenta valor.
    """
    if c.tipo not in {"open_response", "essay"}:
        return []
    solucao = (c.solucao or "").strip()
    if len(solucao) < 80:
        return []
    if not c.criterios_parciais:
        return []  # já apanhado por outro check

    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", s or "").strip().lower()

    needle = _norm(solucao)
    haystack = " ".join(_norm(step.get("descricao", "")) for step in c.criterios_parciais)
    if needle in haystack:
        return []
    return [
        "solucao não espelhada em criterios_parciais — copiar o texto da "
        "resolução completa para a 'descricao' do critério de pontuação máxima "
        "(ver AGENTS.md §6b.0.1)."
    ]


def _validate_criterio(c: CriterioRaw) -> tuple[list[str], list[str]]:
    """
    Retorna (erros, avisos) para um critério.
    Erros → rejeição; avisos → aprovação com suspeitas.
    """
    erros: list[str] = []
    avisos: list[str] = []

    TIPOS_VALIDOS = {"multiple_choice", "open_response", "essay", "complete_table", "multi_select"}
    if c.tipo not in TIPOS_VALIDOS:
        erros.append(f"tipo desconhecido: '{c.tipo}'")
        return erros, avisos

    if not c.reviewed:
        erros.append("critério ainda não foi revisto pelo agente (reviewed: false)")

    # OCR-SUSPECT não resolvido → erro (bloqueia validação)
    erros.extend(_check_ocr_suspects(c))

    if c.tipo == "multiple_choice":
        if not c.resposta_correta or c.resposta_correta.upper() not in _VALID_MC_LETTERS:
            erros.append(
                f"resposta_correta inválida: '{c.resposta_correta}' "
                f"(esperado A, B, C ou D)"
            )

    if c.tipo in {"multi_select", "complete_table"}:
        # Detetar contaminação OCR: nunca deve sobrar uma "Opção (X)" ou letra MC isolada
        if c.resposta_correta:
            erros.append(
                f"tipo '{c.tipo}' não admite resposta_correta MC ('{c.resposta_correta}'); "
                f"usar respostas_corretas (lista) — provável contaminação OCR de 'Opção (X)'."
            )
        if not c.respostas_corretas:
            erros.append(
                f"respostas_corretas vazio para tipo '{c.tipo}': preencher com lista "
                f"(ex: ['I','III','IV']) extraída do PDF CC-VD."
            )
        elif c.tipo == "multi_select" and len(c.respostas_corretas) < 2:
            erros.append(
                f"multi_select requer ≥2 respostas; recebido: {c.respostas_corretas}"
            )

    if c.tipo in {"open_response", "essay", "complete_table", "multi_select"}:
        # Aceitar critérios com níveis de desempenho (PT) — têm campo "nivel" em vez de "pontos" raiz
        has_niveis = any("nivel" in step for step in (c.criterios_parciais or []))
        if not c.solucao or not c.solucao.strip():
            if not has_niveis:
                erros.append("solucao vazia após extração")

        if not c.criterios_parciais:
            # essay sem etapas ainda é válido se for aviso (agente revê)
            if c.tipo == "essay":
                avisos.append("criterios_parciais vazio — níveis de desempenho A/B/C não extraídos; preencher manualmente")
            elif c.tipo in {"complete_table", "multi_select"}:
                # Para estas questões de escolha em PT, a solucao (ex: "Opção (A)") é suficiente
                if not c.solucao or not c.solucao.strip():
                    erros.append("solucao e criterios_parciais vazios")
            else:
                erros.append("criterios_parciais vazio — nenhuma etapa ou nível extraído")

        avisos.extend(_check_token_diff(c))
        erros.extend(_check_solucao_mirrored(c))

    return erros, avisos


def validate_criterios(raw_path: Path) -> tuple[Path, Path]:
    """
    Valida criterios_raw.json e separa aprovados de rejeitados.

    Retorna (approved_path, rejected_path).
    """
    raw_path = raw_path.resolve()
    output_dir = raw_path.parent
    criterios = load_criterios(raw_path)

    n_mirrored = _mirror_complete_table_solucao(criterios)
    if n_mirrored:
        print(f"[cc_validate] 🪞 solucao espelhada em criterios_parciais (complete_table): {n_mirrored} item(ns)")
        dump_criterios(raw_path, criterios)

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
