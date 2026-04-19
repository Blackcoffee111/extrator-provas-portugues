from __future__ import annotations

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
    fonte: str = ""
    status: str = "pending_review"
    observacoes: list[str] = field(default_factory=list)
    texto_original: str = ""
    source_span: dict[str, int] | None = None
    enunciado_contexto_pai: str = ""
    grupo_ids: list[str] = field(default_factory=list)
    descricoes_imagens: dict[str, str] = field(default_factory=dict)
    descricao_breve: str = ""
    solucao: str = ""
    criterios_parciais: list[dict] = field(default_factory=list)
    resolucoes_alternativas: list[str] = field(default_factory=list)
    grupo: str = ""          # "I", "II", … — vazio quando a prova não tem grupos
    reviewed: bool = False   # True após o agente rever e aprovar o item

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
        return cls(
            numero_questao=int(data["numero_questao"]),
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
            fonte=data.get("fonte", ""),
            status=data.get("status", "pending_review"),
            observacoes=list(data.get("observacoes", [])),
            texto_original=data.get("texto_original", ""),
            source_span=data.get("source_span"),
            enunciado_contexto_pai=data.get("enunciado_contexto_pai", ""),
            grupo_ids=list(data.get("grupo_ids", [])),
            descricoes_imagens=dict(data.get("descricoes_imagens", {})),
            descricao_breve=data.get("descricao_breve", ""),
            solucao=data.get("solucao", ""),
            criterios_parciais=list(data.get("criterios_parciais", [])),
            resolucoes_alternativas=list(data.get("resolucoes_alternativas", [])),
            grupo=data.get("grupo", ""),
            reviewed=reviewed,
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


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ── Critérios de Classificação (CC-VD) ────────────────────────────────────────

@dataclass(slots=True)
class CriterioRaw:
    """Critério de classificação extraído do PDF CC-VD, antes do merge com questões."""
    id_item: str                                    # "1", "4.1", "5.2"
    cotacao_total: int                              # pontuação total do item
    tipo: str                                       # "multiple_choice" | "open_response"
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
