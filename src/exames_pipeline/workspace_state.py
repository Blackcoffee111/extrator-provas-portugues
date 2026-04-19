"""Máquina de estados por workspace.

Cada workspace mantém um ``state.json`` na sua raiz com o estado actual
do pipeline. Isto elimina as "regras absolutas em prosa" — o sistema
impõe as transições válidas e recusa operações fora de ordem.

Estados do pipeline principal (ordem estrita):
    fresh → extracted → validated → cc_merged → human_approved → uploaded

Estados do sub-pipeline CC-VD (workspace CC separado):
    cc_fresh → cc_extracted → cc_validated

Regras impostas:
    • run_extract       — recusa se stage >= extracted (a menos que force=True)
    • run_validate      — recusa se stage > validated (protege edições humanas)
    • run_cc_merge      — recusa se stage > validated (idem)
    • run_upload        — recusa se stage != human_approved
    • run_fix_question  — recusa se stage < validated; reseta human_approved → estágio anterior
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# ── Estágios ──────────────────────────────────────────────────────────────────

STAGES = ["fresh", "extracted", "validated", "cc_merged", "human_approved", "uploaded"]
CC_STAGES = ["cc_fresh", "cc_extracted", "cc_validated"]

_STAGE_INDEX = {s: i for i, s in enumerate(STAGES)}
_CC_STAGE_INDEX = {s: i for i, s in enumerate(CC_STAGES)}


# ── Classe principal ──────────────────────────────────────────────────────────

class WorkspaceStage:
    """Lê, valida e grava o estado de um workspace.

    Uso típico em cada tool MCP::

        ws = WorkspaceStage(ws_dir)
        if err := ws.require_not_beyond("validated"):
            return err
        # ... faz o trabalho ...
        ws.transition("cc_merged")
    """

    def __init__(self, ws_dir: Path) -> None:
        self.ws_dir = ws_dir
        self._data: dict = self._load()

    # ── Propriedades de leitura ───────────────────────────────────────────────

    @property
    def stage(self) -> str:
        """Estágio actual, reconciliado com os ficheiros presentes."""
        s = self._data.get("stage", "fresh")
        # Ficheiros de estado são a fonte de verdade irrecusável:
        if (self.ws_dir / ".upload_done").exists():
            return "uploaded"
        if (self.ws_dir / ".review_approved").exists():
            # Só avança para human_approved se o pipeline já chegou a validated/cc_merged
            if _STAGE_INDEX.get(s, 0) >= _STAGE_INDEX["validated"]:
                return "human_approved"
        return s

    @property
    def cc_stage(self) -> str:
        """Estágio do sub-pipeline CC-VD neste workspace."""
        s = self._data.get("cc_stage", "cc_fresh")
        # Reconciliar com ficheiros
        if (self.ws_dir / "criterios_aprovados.json").exists():
            if _CC_STAGE_INDEX.get(s, 0) < _CC_STAGE_INDEX["cc_validated"]:
                return "cc_validated"
        elif (self.ws_dir / "criterios_raw.json").exists():
            if _CC_STAGE_INDEX.get(s, 0) < _CC_STAGE_INDEX["cc_extracted"]:
                return "cc_extracted"
        return s

    # ── Verificações de pré-condição ─────────────────────────────────────────

    def require_at_least(self, min_stage: str) -> str | None:
        """Retorna mensagem de erro se stage < min_stage, caso contrário None."""
        cur = self.stage
        if _STAGE_INDEX.get(cur, 0) < _STAGE_INDEX[min_stage]:
            return (
                f"🛑 Bloqueado: requer estado ≥ '{min_stage}' "
                f"(workspace '{self.ws_dir.name}' está em '{cur}').\n"
                f"Sequência: {' → '.join(STAGES)}"
            )
        return None

    def require_not_beyond(self, max_stage: str) -> str | None:
        """Retorna mensagem de erro se stage > max_stage, caso contrário None."""
        cur = self.stage
        if _STAGE_INDEX.get(cur, 0) > _STAGE_INDEX[max_stage]:
            return (
                f"🛑 Bloqueado: não é possível executar após '{max_stage}' "
                f"(workspace '{self.ws_dir.name}' está em '{cur}').\n"
                f"Esta operação pode destruir trabalho já realizado.\n"
                f"Use run_fix_question para correcções pontuais pós-aprovação."
            )
        return None

    def require_exactly(self, required: str) -> str | None:
        """Retorna mensagem de erro se stage != required, caso contrário None."""
        cur = self.stage
        if cur != required:
            return (
                f"🛑 Bloqueado: requer estado '{required}' "
                f"(workspace '{self.ws_dir.name}' está em '{cur}')."
            )
        return None

    def require_cc_at_least(self, min_cc: str) -> str | None:
        cur = self.cc_stage
        if _CC_STAGE_INDEX.get(cur, 0) < _CC_STAGE_INDEX[min_cc]:
            return (
                f"🛑 Bloqueado: sub-pipeline CC requer ≥ '{min_cc}' "
                f"(está em '{cur}').\n"
                f"Sequência CC: {' → '.join(CC_STAGES)}"
            )
        return None

    # ── Transições ────────────────────────────────────────────────────────────

    def transition(self, new_stage: str) -> None:
        """Avança o estágio (só para frente) e grava state.json."""
        if _STAGE_INDEX.get(new_stage) is None:
            raise ValueError(f"Estágio desconhecido: '{new_stage}'")
        cur_idx = _STAGE_INDEX.get(self._data.get("stage", "fresh"), 0)
        new_idx = _STAGE_INDEX[new_stage]
        if new_idx > cur_idx:
            self._data["stage"] = new_stage
            self._data["updated_at"] = _now()
            self._save()

    def transition_cc(self, new_cc_stage: str) -> None:
        """Avança o estágio CC (só para frente) e grava state.json."""
        if _CC_STAGE_INDEX.get(new_cc_stage) is None:
            raise ValueError(f"Estágio CC desconhecido: '{new_cc_stage}'")
        cur_idx = _CC_STAGE_INDEX.get(self._data.get("cc_stage", "cc_fresh"), 0)
        new_idx = _CC_STAGE_INDEX[new_cc_stage]
        if new_idx > cur_idx:
            self._data["cc_stage"] = new_cc_stage
            self._data["updated_at"] = _now()
            self._save()

    def reset_to(self, target_stage: str) -> None:
        """Retrocede o estágio (usado por run_fix_question após resetar aprovação)."""
        if _STAGE_INDEX.get(target_stage) is None:
            raise ValueError(f"Estágio desconhecido: '{target_stage}'")
        self._data["stage"] = target_stage
        self._data["updated_at"] = _now()
        self._save()

    # ── I/O ───────────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        state_path = self.ws_dir / "state.json"
        if state_path.exists():
            try:
                data = json.loads(state_path.read_text(encoding="utf-8"))
                # Validar campos conhecidos
                if data.get("stage") not in STAGES:
                    data["stage"] = self._infer_stage_from_files()
                if data.get("cc_stage") not in CC_STAGES:
                    data["cc_stage"] = "cc_fresh"
                return data
            except Exception:
                pass
        # Inferir estado a partir dos ficheiros existentes (workspaces antigos sem state.json)
        return {
            "stage": self._infer_stage_from_files(),
            "cc_stage": "cc_fresh",
            "workspace": self.ws_dir.name,
            "created_at": _now(),
            "updated_at": _now(),
        }

    def _infer_stage_from_files(self) -> str:
        """Infere o estágio a partir dos ficheiros presentes (compatibilidade retroativa)."""
        ws = self.ws_dir
        if (ws / ".upload_done").exists():
            return "uploaded"
        if (ws / ".review_approved").exists():
            return "human_approved"
        if (ws / "questoes_final.json").exists():
            return "cc_merged"
        if (ws / "questoes_aprovadas.json").exists():
            return "validated"
        if (ws / "questoes_raw.json").exists():
            return "extracted"
        return "fresh"

    def _save(self) -> None:
        self.ws_dir.mkdir(parents=True, exist_ok=True)
        state_path = self.ws_dir / "state.json"
        state_path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
