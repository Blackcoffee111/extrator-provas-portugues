"""
Re-upload das imagens re-extraídas para Supabase Storage.

Sobrescreve os blobs existentes (via PUT quando há 409 Duplicate). Mesmo path
= mesma URL pública, logo não precisa tocar em nenhuma linha da DB.

NÃO mexe em questões, contextos ou qualquer tabela — apenas o bucket de mídia.
"""
from __future__ import annotations

import os
import sys
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path("/Users/adrianoushinohama/dev/Exames Nacionais/Provas de portugues")
WORKTREE = PROJECT_ROOT / ".claude/worktrees/strange-feynman-2864c8"

sys.path.insert(0, str(WORKTREE / "src"))

# Carrega .env manualmente (config.load_settings já faz isto via python-dotenv
# se instalado; aqui reproduzo à mão para evitar dependência)
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from exames_pipeline.config import load_settings  # noqa: E402
from exames_pipeline.supabase_client import _sb_headers, _upload_binary  # noqa: E402


WORKSPACES = [
    "EX-Port639-F1-2023_net",
    "EX-Port639-F2-2023_net",
    "EX-Port639-EE-2024_net",
    "EX-Port639-F1-2024_net",
    "EX-Port639-F2-2024_net",
]


def main() -> None:
    settings = load_settings(PROJECT_ROOT)
    if not settings.supabase_url or not settings.supabase_key:
        print("❌ SUPABASE_URL / SUPABASE_KEY não configurados.")
        sys.exit(1)
    headers = _sb_headers(settings)

    total_uploaded = 0
    total_failed = 0

    for ws_name in WORKSPACES:
        images_dir = PROJECT_ROOT / "workspace" / ws_name / "imagens_extraidas"
        if not images_dir.exists():
            print(f"⚠️  {ws_name}: pasta imagens_extraidas/ ausente — skip")
            continue

        images = sorted(images_dir.glob("*.jpg")) + sorted(images_dir.glob("*.jpeg")) + sorted(images_dir.glob("*.png"))
        if not images:
            print(f"⚠️  {ws_name}: nenhuma imagem — skip")
            continue

        print(f"\n=== {ws_name} ({len(images)} imagem(ns)) ===")
        for img in images:
            object_name = f"{ws_name}/{img.name}"
            encoded = urllib.parse.quote(object_name, safe="/")
            upload_url = (f"{settings.supabase_url}/storage/v1/object/"
                          f"{settings.supabase_bucket}/{encoded}")
            try:
                _upload_binary(upload_url, headers, img)
                size_kb = img.stat().st_size / 1024
                print(f"  ✅ {img.name[:16]}… ({size_kb:.1f} KB)")
                total_uploaded += 1
            except Exception as exc:
                print(f"  ❌ {img.name[:16]}… — {exc}")
                total_failed += 1

    print(f"\n{'='*50}")
    print(f"✅ {total_uploaded} imagens re-uploaded")
    if total_failed:
        print(f"❌ {total_failed} falhas")
        sys.exit(1)


if __name__ == "__main__":
    main()
