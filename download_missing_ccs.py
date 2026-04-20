#!/usr/bin/env python3
"""
Script para baixar CCs (Critérios de Classificação) em falta do site do IAVE.

Estratégia:
  Para cada arquivo em falta, tenta todos os meses (01-12) na URL do WordPress do IAVE:
    https://iave.pt/wp-content/uploads/YYYY/MM/NOME.pdf
  Usa HEAD requests para encontrar a URL válida antes de baixar.
"""

import os
import requests
from pathlib import Path

BASE = Path("/Users/adrianoushinohama/Desktop/Exames Nacionais/Provas de portugues/provas fonte")
IAVE_BASE = "https://iave.pt/wp-content/uploads"

# Lista de arquivos em falta:
# (nome_do_arquivo, caminho_relativo_destino, meses_prováveis)
# meses_prováveis: 1ª Fase → mai/jun, 2ª Fase → set/out, EE → jan/fev
MISSING = [
    # ── Português – 639 ─────────────────────────────────────────────────────
    # 1ª Fase: falta CC (2016-2023)
    ("EX-Port639-F1-2016-CC-VD_net.pdf",  "Português – 639/2016/1ª Fase", [5,6,7,8]),
    ("EX-Port639-F1-2017-CC-VD_net.pdf",  "Português – 639/2017/1ª Fase", [5,6,7,8]),
    ("EX-Port639-F1-2018-CC-VD_net.pdf",  "Português – 639/2018/1ª Fase", [5,6,7,8]),
    ("EX-Port639-F1-2019-CC-VD_net.pdf",  "Português – 639/2019/1ª Fase", [5,6,7,8]),
    ("EX-Port639-F1-2020-CC-VD_net.pdf",  "Português – 639/2020/1ª Fase", [5,6,7,8]),
    ("EX-Port639-F1-2021-CC-VD_net.pdf",  "Português – 639/2021/1ª Fase", [5,6,7,8]),
    ("EX-Port639-F1-2022-CC-VD_net.pdf",  "Português – 639/2022/1ª Fase", [5,6,7,8]),
    ("EX-Port639-F1-2023-CC-VD_net.pdf",  "Português – 639/2023/1ª Fase", [5,6,7,8]),
    # 2ª Fase: falta CC (2016, 2017, 2018, 2020, 2022)
    ("EX-Port639-F2-2016-CC-VD_net.pdf",  "Português – 639/2016/2ª Fase", [9,10,11,12]),
    ("EX-Port639-F2-2017-CC-VD_net.pdf",  "Português – 639/2017/2ª Fase", [9,10,11,12]),
    ("EX-Port639-F2-2018-CC-VD_net.pdf",  "Português – 639/2018/2ª Fase", [9,10,11,12]),
    ("EX-Port639-F2-2020-CC-VD_net.pdf",  "Português – 639/2020/2ª Fase", [9,10,11,12]),
    ("EX-Port639-F2-2022-CC-VD_net.pdf",  "Português – 639/2022/2ª Fase", [9,10,11,12]),

    # ── Português Língua Segunda – 138 ──────────────────────────────────────
    ("EX-Port138-F1-2018-CC-VD_net.pdf",  "Português Língua Segunda – 138/2018/1ª Fase", [5,6,7,8]),
    ("EX-Port138-F2-2018-CC-VD_net.pdf",  "Português Língua Segunda – 138/2018/2ª Fase", [9,10,11,12]),
    ("EX-Port138-F1-2019-CC-VD_net.pdf",  "Português Língua Segunda – 138/2019/1ª Fase", [5,6,7,8]),
    ("EX-Port138-F2-2019-CC-VD_net.pdf",  "Português Língua Segunda – 138/2019/2ª Fase", [9,10,11,12]),
    ("EX-Port138-F1-2022-CC-VD_net.pdf",  "Português Língua Segunda – 138/2022/1ª Fase", [5,6,7,8]),
]

# Variantes de nome a tentar (alguns anos usam sufixo diferente)
def name_variants(name: str) -> list[str]:
    """Gera variações do nome para cobrir discrepâncias históricas."""
    variants = [name]
    if name.endswith("_net.pdf"):
        variants.append(name.replace("_net.pdf", ".pdf"))   # sem _net
    elif name.endswith(".pdf"):
        stem = name[:-4]
        variants.append(stem + "_net.pdf")                  # com _net
    return variants


def find_url(filename: str, year: int, months: list[int]) -> str | None:
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (compatible; IAVE-downloader/1.0; +adrianozuardi@gmail.com)"
    )
    for variant in name_variants(filename):
        for month in months:
            url = f"{IAVE_BASE}/{year}/{month:02d}/{variant}"
            try:
                r = session.head(url, timeout=8, allow_redirects=True)
                if r.status_code == 200:
                    print(f"  ✓ Encontrado: {url}")
                    return url
            except requests.RequestException:
                pass
    return None


def download(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, timeout=30, stream=True)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
        print(f"  ⬇  Baixado → {dest.name}")
        return True
    except Exception as e:
        print(f"  ✗ Erro ao baixar {url}: {e}")
        return False


def main():
    found, skipped, failed = 0, 0, 0

    for filename, rel_dir, months in MISSING:
        dest = BASE / rel_dir / filename
        if dest.exists():
            print(f"[JÁ EXISTE] {rel_dir}/{filename}")
            skipped += 1
            continue

        print(f"[BUSCANDO] {rel_dir}/{filename}")
        year = int(rel_dir.split("/")[1])  # extrai ano do caminho
        url = find_url(filename, year, months)

        if url:
            if download(url, dest):
                found += 1
            else:
                failed += 1
        else:
            print(f"  ✗ Não encontrado no IAVE (tente buscar manualmente)")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Resultado: {found} baixados, {skipped} já existiam, {failed} não encontrados")


if __name__ == "__main__":
    main()
