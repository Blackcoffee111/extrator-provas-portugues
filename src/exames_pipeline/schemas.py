from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json


@dataclass(slots=True)
class Alternative:
    letra: str
    texto: str


@dataclass(slots=True)
class Question:
    numero_questao: int
    enunciado: str
    alternativas: list[Alternative] = field(default_factory=list)
    id_item: str = ""
    ordem_item: int | None = None
    numero_principal: int | None = None
    subitem: str | None = None
    tipo_item: str = "unknown"
    materia: str = ""
    tema: str = ""
    subtema: str = ""
    tags: list[str] = field(default_factory=list)
    imagens: list[str] = field(default_factory=list)
    imagens_contexto: list[str] = field(default_factory=list)
    pagina_origem: int | None = None
    resposta_correta: str | None = None
    respostas_corretas: list[str] = field(default_factory=list)
    fonte: str = ""
    status: str = "pending_review"
    observacoes: list[str] = field(default_factory=list)
    texto_original: str = ""
    source_span: dict[str, int] | None = None
    enunciado_contexto_pai: str = ""
    id_contexto_pai: str = ""   # ID do context_stem pai (ex: "I-ctx1", "II-ctx1")
    grupo_ids: list[str] = field(default_factory=list)
    descricoes_imagens: dict[str, str] = field(default_factory=dict)
    descricao_breve: str = ""
    solucao: str = ""
    criterios_parciais: list[dict] = field(default_factory=list)
    resolucoes_alternativas: list[str] = field(default_factory=list)
    grupo: str = ""          # "I", "II", … — vazio quando a prova não tem grupos
    parte: str = ""          # "A", "B", "C" — vazio quando o grupo não tem partes
    reviewed: bool = False   # True após o agente rever e aprovar o item
    # ── Campos específicos de Português ──────────────────────────────────────
    pool_opcional: str = ""              # "I-opt", "II-opt"; vazio = item obrigatório
    palavras_min: int | None = None      # Grupo III: limite mínimo de palavras
    palavras_max: int | None = None      # Grupo III: limite máximo de palavras
    linhas_referenciadas: list[str] = field(default_factory=list)
    # Parâmetros A/B/C da dissertação:
    # [{"parametro":"A","nome":"Conteúdo","niveis":[{"nivel":"N5","pontos":12,"descritor":"..."}]}]
    parametros_classificacao: list[dict] = field(default_factory=list)
    # Gate de numeração de linhas em context_stem (Português).
    # None = por verificar; True = texto tem marcadores de linha formatados;
    # False = texto não tem numeração. Obrigatório preencher antes do validate.
    tem_numeracao_linhas: bool | None = None
    # True só depois de o agente conferir o PDF original e aplicar o formato canónico
    # ("\n{N} " em início de linha) a todos os marcadores presentes.
    linhas_verificadas: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Question":
        alternativas = [
            alt if isinstance(alt, Alternative) else Alternative(**alt)
            for alt in data.get("alternativas", [])
        ]
        # Migração retrocompatível: ficheiros antigos sem campo "reviewed" usam
        # a presença de "[review-pending]" nas observacoes para inferir o estado.
        if "reviewed" in data:
            reviewed = bool(data["reviewed"])
        else:
            reviewed = not any("review-pending" in obs for obs in data.get("observacoes", []))
        # Inferir numero_questao do id_item quando o campo estiver ausente
        # (itens adicionados manualmente ao questoes_review.json sem entrada correspondente no meta)
        if "numero_questao" in data:
            numero_questao = int(data["numero_questao"])
        else:
            _m = re.match(r"^(?:[IVX]+-)?(\d{1,3})", data.get("id_item", "0"))
            numero_questao = int(_m.group(1)) if _m else 0
        return cls(
            numero_questao=numero_questao,
            enunciado=data.get("enunciado", ""),
            alternativas=alternativas,
            id_item=data.get("id_item", ""),
            ordem_item=data.get("ordem_item"),
            numero_principal=data.get("numero_principal"),
            subitem=data.get("subitem"),
            tipo_item=data.get("tipo_item", "unknown"),
            materia=data.get("materia", ""),
            tema=data.get("tema", ""),
            subtema=data.get("subtema", ""),
            tags=list(data.get("tags", [])),
            imagens=list(data.get("imagens", [])),
            imagens_contexto=list(data.get("imagens_contexto", [])),
            pagina_origem=data.get("pagina_origem"),
            resposta_correta=data.get("resposta_correta"),
            respostas_corretas=list(data.get("respostas_corretas", [])),
            fonte=data.get("fonte", ""),
            status=data.get("status", "pending_review"),
            observacoes=list(data.get("observacoes", [])),
            texto_original=data.get("texto_original", ""),
            source_span=data.get("source_span"),
            enunciado_contexto_pai=data.get("enunciado_contexto_pai", ""),
            id_contexto_pai=data.get("id_contexto_pai", ""),
            grupo_ids=list(data.get("grupo_ids", [])),
            descricoes_imagens=dict(data.get("descricoes_imagens", {})),
            descricao_breve=data.get("descricao_breve", ""),
            solucao=data.get("solucao", ""),
            criterios_parciais=list(data.get("criterios_parciais", [])),
            resolucoes_alternativas=list(data.get("resolucoes_alternativas", [])),
            grupo=data.get("grupo", ""),
            parte=data.get("parte", ""),
            reviewed=reviewed,
            pool_opcional=data.get("pool_opcional", ""),
            palavras_min=data.get("palavras_min"),
            palavras_max=data.get("palavras_max"),
            linhas_referenciadas=list(data.get("linhas_referenciadas", [])),
            parametros_classificacao=list(data.get("parametros_classificacao", [])),
            tem_numeracao_linhas=data.get("tem_numeracao_linhas"),
            linhas_verificadas=bool(data.get("linhas_verificadas", False)),
        )


@dataclass(slots=True)
class EstruturaCotacoes:
    total_itens_principais: int
    estrutura: dict[str, list[str]]  # "1" -> ["1.1", "1.2"]; "2" -> []
    cotacoes: dict[str, int]          # "1.1" -> 10, "2" -> 20
    confianca: str = "alta"           # "alta" | "media" | "baixa"
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EstruturaCotacoes":
        return cls(
            total_itens_principais=int(data.get("total_itens_principais", 0)),
            estrutura={str(k): list(v) for k, v in data.get("estrutura", {}).items()},
            cotacoes={str(k): int(v) for k, v in data.get("cotacoes", {}).items()},
            confianca=data.get("confianca", "alta"),
            raw_response=data.get("raw_response", ""),
        )


def dump_cotacoes(path: Path, estrutura: EstruturaCotacoes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(estrutura.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_cotacoes(path: Path) -> EstruturaCotacoes:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return EstruturaCotacoes.from_dict(raw)


def dump_questions(path: Path, questions: list[Question]) -> None:
    payload = [question.to_dict() for question in questions]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_questions(path: Path) -> list[Question]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Question.from_dict(item) for item in raw]


# ── Campos expostos ao agente durante revisão ─────────────────────────────────
# Tudo o que não está aqui vai para questoes_meta.json (uso interno do validador).
REVIEW_FIELDS: frozenset[str] = frozenset({
    "id_item",               # chave de lookup
    "tipo_item",             # MC / open / essay / complete_table / multi_select
    "enunciado",             # texto a rever/corrigir
    "alternativas",          # opções MC
    "resposta_correta",      # GRUPO I MC — agente preenche
    "respostas_corretas",    # multi_select / complete_table — agente preenche (lista)
    "tema",                  # categorização
    "subtema",               # categorização
    "descricao_breve",       # categorização
    "tags",                  # categorização
    "observacoes",           # alertas da extração
    "reviewed",              # gate do validate
    "imagens",               # refs de imagens a verificar
    "enunciado_contexto_pai",# contexto do group stem para subitens
    "id_contexto_pai",        # ID do context_stem pai (ex: "I-ctx1")
    "grupo",                 # "I", "II", "III"
    "parte",                 # "A", "B", "C" (só GRUPO I em provas PT)
    "solucao",               # questões abertas / dissertação
    # Campos Português
    "pool_opcional",         # "I-opt", "II-opt" ou vazio
    "palavras_min",          # Grupo III
    "palavras_max",          # Grupo III
    "linhas_referenciadas",  # ["16", "29-30"] — linhas citadas no enunciado
    "parametros_classificacao",  # parâmetros A/B/C dissertação
    "tem_numeracao_linhas",  # context_stem: True/False/null — agente decide
    "linhas_verificadas",    # context_stem: gate obrigatório após conferir PDF
})


def split_question_for_review(q_dict: dict) -> tuple[dict, dict]:
    """Divide um item em (review_dict, meta_dict).

    review_dict — apenas REVIEW_FIELDS: o agente lê e edita este ficheiro.
    meta_dict   — tudo o resto + id_item: usado internamente pelo validador.
    O merge de ambos reconstrói o item completo em questoes_raw.json.
    """
    review = {k: v for k, v in q_dict.items() if k in REVIEW_FIELDS}
    # id_item sempre presente no meta para servir de chave de merge
    meta = {"id_item": q_dict.get("id_item", "")}
    meta.update({k: v for k, v in q_dict.items() if k not in REVIEW_FIELDS})
    return review, meta


def merge_review_into_full(review: dict, meta: dict) -> dict:
    """Reconstrói um item completo a partir de review + meta."""
    return {**meta, **review}


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ── Notas de rodapé de textos-âncora (Português) ─────────────────────────────

@dataclass(slots=True)
class NotaRodape:
    numero: str   # "1", "2", …
    texto: str    # "calamistrar – tornar crespo ou frisado"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NotaRodape":
        return cls(numero=str(data.get("numero", "")), texto=data.get("texto", ""))


# ── Critérios de Classificação (CC-VD) ────────────────────────────────────────

@dataclass(slots=True)
class CriterioRaw:
    """Critério de classificação extraído do PDF CC-VD, antes do merge com questões."""
    id_item: str                                    # "1", "4.1", "5.2"
    cotacao_total: int                              # pontuação total do item
    tipo: str                                       # "multiple_choice" | "open_response" | "multi_select" | "complete_table" | "essay"
    resposta_correta: str | None                    # "B" para MC; None para aberta
    solucao: str                                    # solução completa LaTeX/Markdown
    criterios_parciais: list[dict]                  # [{"pontos": N, "descricao": "..."}]
    resolucoes_alternativas: list[str]              # processos alternativos
    status: str                                     # "parsed" | "pending_review" | "approved"
    texto_original: str                             # bloco bruto do markdown CC
    fonte: str = ""                                 # ex: "EX-MatA635-F1-2023-CC-VD"
    observacoes: list[str] = field(default_factory=list)
    imagens: list[str] = field(default_factory=list)  # paths das imagens referenciadas no bloco
    contexto: str = ""                              # texto introdutório antes do primeiro processo
    reviewed: bool = False   # True após o agente rever e aprovar o critério
    respostas_corretas: list[str] = field(default_factory=list)  # multi_select: ["I","III","IV"]; complete_table: pares chave→opção

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CriterioRaw":
        if "reviewed" in data:
            reviewed = bool(data["reviewed"])
        else:
            reviewed = not any("review-pending" in obs for obs in data.get("observacoes", []))
        return cls(
            id_item=str(data["id_item"]),
            cotacao_total=int(data["cotacao_total"]),
            tipo=data.get("tipo", "unknown"),
            resposta_correta=data.get("resposta_correta"),
            solucao=data.get("solucao", ""),
            criterios_parciais=list(data.get("criterios_parciais", [])),
            resolucoes_alternativas=list(data.get("resolucoes_alternativas", [])),
            status=data.get("status", "pending_review"),
            texto_original=data.get("texto_original", ""),
            fonte=data.get("fonte", ""),
            observacoes=list(data.get("observacoes", [])),
            imagens=list(data.get("imagens", [])),
            contexto=data.get("contexto", ""),
            reviewed=reviewed,
            respostas_corretas=list(data.get("respostas_corretas", [])),
        )


def dump_criterios(path: Path, criterios: list[CriterioRaw]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([c.to_dict() for c in criterios], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_criterios(path: Path) -> list[CriterioRaw]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [CriterioRaw.from_dict(item) for item in raw]
