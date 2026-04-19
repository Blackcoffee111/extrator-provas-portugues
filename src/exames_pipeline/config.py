from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")  # remove aspas opcionais
        # Não sobrescrever variáveis já definidas no ambiente, nem valores vazios
        if value:
            os.environ.setdefault(key.strip(), value)


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    project_root: Path
    workdir: Path
    pdf_parser_backend: str
    pdf_parser_command: str
    mineru_binary: str
    mineru_backend: str
    mineru_lang: str
    mineru_python_bin: str
    mineru_venv: Path
    mineru_mode: str
    mineru_method: str
    mineru_formula_enable: bool
    mineru_table_enable: bool
    supabase_url: str
    supabase_key: str
    supabase_bucket: str
    supabase_table: str


def load_settings(project_root: Path | None = None) -> Settings:
    # PIPELINE_ROOT tem prioridade — definido pelo .mcp.json e scripts
    env_root = os.environ.get("PIPELINE_ROOT")
    root = Path(env_root) if env_root else (project_root or Path.cwd())
    _load_dotenv(root / ".env")
    workdir = Path(os.environ.get("PIPELINE_WORKDIR", "./workspace"))
    if not workdir.is_absolute():
        workdir = (root / workdir).resolve()

    return Settings(
        project_root=root.resolve(),
        workdir=workdir,
        pdf_parser_backend=os.environ.get("PDF_PARSER_BACKEND", "mineru"),
        pdf_parser_command=os.environ.get("PDF_PARSER_COMMAND", "").strip(),
        mineru_binary=os.environ.get("MINERU_BINARY", "").strip(),
        mineru_backend=os.environ.get("MINERU_BACKEND", "pipeline").strip(),
        mineru_lang=os.environ.get("MINERU_LANG", "pt").strip(),
        mineru_python_bin=os.environ.get("MINERU_PYTHON_BIN", "python3.12").strip(),
        mineru_venv=(root / os.environ.get("MINERU_VENV", "./.venv-mineru")).resolve(),
        mineru_mode=os.environ.get("MINERU_MODE", "math_heavy").strip().lower(),
        mineru_method=os.environ.get("MINERU_METHOD", "ocr").strip().lower(),
        mineru_formula_enable=_env_flag("MINERU_FORMULA_ENABLE", True),
        mineru_table_enable=_env_flag("MINERU_TABLE_ENABLE", False),
        supabase_url=os.environ.get("SUPABASE_URL", "").strip(),
        supabase_key=os.environ.get("SUPABASE_KEY", "").strip(),
        supabase_bucket=os.environ.get("SUPABASE_BUCKET", "questoes-media"),
        supabase_table=os.environ.get("SUPABASE_TABLE", "questoes"),
    )
