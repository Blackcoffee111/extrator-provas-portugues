"""
Módulo CC-OCR-Lint — Detecção heurística de artefactos OCR em criterios_raw.json.

Roda automaticamente após cc_extract, antes da revisão do agente.
Adiciona "OCR-SUSPECT: <tipo> '<trecho>'" nas observacoes de cada item suspeito.
Gera criterios_ocr_flags.json com apenas os itens flaggeados (compacto).

Sem whitelist de vocabulário — aplicável a qualquer disciplina.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


# ── Padrões OCR heurísticos ───────────────────────────────────────────────────

# I maiúsculo lido como l minúsculo (ex: "Iogo" → "logo").
# Exige ≥ 3 letras minúsculas após o I para reduzir falsos positivos.
_OCR_CAPITAL_I_RE = re.compile(
    r'\bI[a-záàâãéêíóôõúA-ZÁÀÂÃÉÊÍÓÔÕÚ]{0,2}[a-záàâãéêíóôõú]{1}[a-z]{1,}\b'
)

# 0 (zero) no interior de uma sequência alfabética (ex: "l0go" → "logo", "c0m" → "com").
_OCR_ZERO_IN_WORD_RE = re.compile(
    r'[a-záàâãéêíóôõúA-ZÁÀÂÃÉÊÍÓÔÕÚ]0[a-záàâãéêíóôõúA-ZÁÀÂÃÉÊÍÓÔÕÚ]'
)

# \frac{...} sem denominador {…} imediatamente a seguir.
_FRAC_NO_DENOM_RE = re.compile(r'\\frac\{[^}]*\}(?!\s*\{)')

# \sqrt sem chaves de argumento (ex: "\sqrt2" em vez de "\sqrt{2}").
_SQRT_NO_BRACE_RE = re.compile(r'\\sqrt(?!\s*\{)(?=[^\s\\$])')

# ^ ou _ com argumento de mais de 1 caracter sem chaves (ex: "x^ab" em vez de "x^{ab}").
_EXPOSED_SUPERSCRIPT_RE = re.compile(r'(?<![\\{])\^[a-zA-Z]{2,}(?![}])')
_EXPOSED_SUBSCRIPT_RE   = re.compile(r'(?<![\\{])_[a-zA-Z]{2,}(?![}])')


# ── Funções de verificação ────────────────────────────────────────────────────

def _check_dollar_balance(text: str) -> list[str]:
    """$ não balanceado em LaTeX inline (número ímpar de $ não-duplos)."""
    # Substituir $$ para não interferir na contagem
    cleaned = re.sub(r'\$\$', '  ', text)
    count = cleaned.count('$')
    if count % 2 != 0:
        # Contexto em redor da primeira ocorrência
        pos = cleaned.index('$')
        snippet = text[max(0, pos - 10):pos + 20].replace('\n', ' ').strip()
        return [f"OCR-SUSPECT: latex_dollar_impar '{snippet}'"]
    return []


def _check_parens_balance(text: str) -> list[str]:
    """Parênteses ou colchetes desbalanceados (tolerância ±1 para contextos intencionais)."""
    # Remover LaTeX (\left, \right, etc.) e matemática inline para evitar falsos positivos
    clean = re.sub(r'\\(?:left|right|big[lr]?)\s*[\(\)\[\]]', '', text)
    clean = re.sub(r'\$[^$]*\$', '', clean)
    clean = re.sub(r'\$\$[\s\S]*?\$\$', '', clean)

    flags = []
    diff_p = clean.count('(') - clean.count(')')
    diff_b = clean.count('[') - clean.count(']')
    if abs(diff_p) > 1:
        flags.append(
            f"OCR-SUSPECT: parens_imbalanced "
            f"'({clean.count('(')} abertos, {clean.count(')')} fechados)'"
        )
    if abs(diff_b) > 1:
        flags.append(
            f"OCR-SUSPECT: brackets_imbalanced "
            f"'[{clean.count('[')} abertos, {clean.count(']')} fechados]'"
        )
    return flags


def _lint_text(text: str, field: str = "") -> list[str]:
    """Aplica todas as heurísticas OCR a um texto e devolve lista de flags."""
    if not text or not text.strip():
        return []

    flags: list[str] = []
    p = f"[{field}] " if field else ""

    # 1. $ não balanceado
    flags.extend(f"{p}{f}" for f in _check_dollar_balance(text))

    # 2. \frac sem denominador
    for m in _FRAC_NO_DENOM_RE.finditer(text):
        snippet = text[max(0, m.start() - 5):m.end() + 12].replace('\n', ' ').strip()
        flags.append(f"{p}OCR-SUSPECT: latex_frac_sem_denom '{snippet}'")

    # 3. \sqrt sem chaves
    for m in _SQRT_NO_BRACE_RE.finditer(text):
        snippet = text[max(0, m.start() - 3):m.end() + 8].replace('\n', ' ').strip()
        flags.append(f"{p}OCR-SUSPECT: latex_sqrt_sem_chaves '{snippet}'")

    # 4. Parênteses/colchetes desbalanceados
    flags.extend(f"{p}{f}" for f in _check_parens_balance(text))

    # 5. I maiúsculo lido como l (OCR)
    for m in _OCR_CAPITAL_I_RE.finditer(text):
        word = m.group()
        # Excluir siglas e nomes próprios óbvios: token todo maiúsculas não é OCR de l
        if word == word.upper():
            continue
        # Excluir se o token começa com maiúscula esperada (início de frase — heurística: após ". ")
        ctx_before = text[max(0, m.start() - 2):m.start()]
        if ctx_before.strip().endswith('.'):
            continue
        flags.append(f"{p}OCR-SUSPECT: ocr_i_maiusculo '{word}'")

    # 6. 0 (zero) dentro de palavra alfabética
    for m in _OCR_ZERO_IN_WORD_RE.finditer(text):
        snippet = text[max(0, m.start() - 2):m.end() + 2].replace('\n', ' ').strip()
        flags.append(f"{p}OCR-SUSPECT: ocr_zero_em_palavra '{snippet}'")

    # 7. ^ ou _ expostos com argumento multi-caracter sem chaves
    for m in _EXPOSED_SUPERSCRIPT_RE.finditer(text):
        flags.append(f"{p}OCR-SUSPECT: latex_exp_sem_chaves '{m.group()}'")
    for m in _EXPOSED_SUBSCRIPT_RE.finditer(text):
        flags.append(f"{p}OCR-SUSPECT: latex_sub_sem_chaves '{m.group()}'")

    return flags


# ── Ponto de entrada público ──────────────────────────────────────────────────

def lint_criterios(raw_path: Path) -> tuple[Path, int]:
    """Lê criterios_raw.json, adiciona flags OCR-SUSPECT e grava criterios_ocr_flags.json.

    Modifica criterios_raw.json in-place (só adiciona observações — não remove nem altera campos).
    Devolve (flags_path, n_flagged).
    """
    raw_path = raw_path.resolve()
    output_dir = raw_path.parent
    flags_path = output_dir / "criterios_ocr_flags.json"

    try:
        criterios: list[dict] = json.loads(raw_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[cc_ocr_lint] ❌ Erro ao ler {raw_path.name}: {exc}")
        flags_path.write_text("[]", encoding="utf-8")
        return flags_path, 0

    flagged_summary: list[dict] = []
    modified = False

    for c in criterios:
        item_flags: list[str] = []

        # Verificar bloco OCR bruto
        item_flags.extend(_lint_text(c.get("texto_original", ""), "original"))

        # Verificar campos editáveis (os que o agente vê em criterios_review.json)
        item_flags.extend(_lint_text(c.get("solucao", ""), "solucao"))
        for i, step in enumerate(c.get("criterios_parciais", []), start=1):
            item_flags.extend(_lint_text(step.get("descricao", ""), f"etapa{i}"))
        for i, alt in enumerate(c.get("resolucoes_alternativas", []), start=1):
            item_flags.extend(_lint_text(alt, f"alt{i}"))

        if item_flags:
            obs: list[str] = list(c.get("observacoes", []))
            existing = set(obs)
            new_flags = [f for f in item_flags if f not in existing]
            if new_flags:
                obs.extend(new_flags)
                c["observacoes"] = obs
                modified = True

            flagged_summary.append({
                "id_item":  c["id_item"],
                "tipo":     c.get("tipo", ""),
                "n_flags":  len(item_flags),
                "flags":    item_flags,
            })
            print(f"[cc_ocr_lint] ⚠️  {c['id_item']} — {len(item_flags)} suspeita(s)")
        else:
            print(f"[cc_ocr_lint] ✅ {c['id_item']}")

    if modified:
        raw_path.write_text(
            json.dumps(criterios, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    flags_path.write_text(
        json.dumps(flagged_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    n = len(flagged_summary)
    if n:
        print(f"\n[cc_ocr_lint] ⚠️  {n} item(ns) com suspeitas OCR → {flags_path.name}")
    else:
        print(f"\n[cc_ocr_lint] ✅ Nenhuma suspeita OCR detectada.")

    return flags_path, n
