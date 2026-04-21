"""Testes de validação canônica de fonte/matéria.

Cobre os bugs reais encontrados em produção (ver migração de 2026-04-21
no projeto de Matemática):
  - 'Matematica A' sem acento
  - 'Matemática' sem o "A"
  - 'Prova 635' parseado como matéria
  - fase=None para "Época Especial"
  - 'Desconhecido' fallback silencioso

Executar: python3.11 -m unittest tests.test_fonte_validation
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from exames_pipeline.supabase_client import (  # noqa: E402
    FASES_CANONICAS,
    FonteInvalidaError,
    MATERIAS_CANONICAS,
    TIPOS_CANONICOS,
    _parse_fonte,
)


class TestParseFonteCanonica(unittest.TestCase):
    """Casos válidos devem ser parseados corretamente."""

    def test_portugues_primeira_fase(self):
        r = _parse_fonte("Exame Nacional, Português, 1.ª Fase, 2024")
        self.assertEqual(r, {"tipo": "Exame Nacional", "materia": "Português",
                             "fase": "1.ª Fase", "ano": 2024})

    def test_portugues_segunda_fase(self):
        r = _parse_fonte("Exame Nacional, Português, 2.ª Fase, 2023")
        self.assertEqual(r["fase"], "2.ª Fase")

    def test_portugues_epoca_especial(self):
        # bug histórico: fase ficava NULL para Época Especial
        r = _parse_fonte("Exame Nacional, Português, Época Especial, 2024")
        self.assertEqual(r["fase"], "Época Especial")

    def test_matematica(self):
        r = _parse_fonte("Exame Nacional, Matemática A, 1.ª Fase, 2024")
        self.assertEqual(r["materia"], "Matemática A")


class TestParseFonteRejeicao(unittest.TestCase):
    """Qualquer desvio do formato canônico deve levantar FonteInvalidaError."""

    def _assert_invalid(self, fonte: str):
        with self.assertRaises(FonteInvalidaError):
            _parse_fonte(fonte)

    # — bugs reais que já chegaram ao DB antes —
    def test_materia_sem_acento(self):
        self._assert_invalid("Exame Nacional, Matematica A, 1.ª Fase, 2014")

    def test_materia_sem_letra_a(self):
        self._assert_invalid("Exame Nacional, Matemática, 1.ª Fase, 2016")

    def test_tipo_nao_canonico(self):
        self._assert_invalid(
            "Exame Final Nacional de Matemática A, Prova 635, Época Especial, 2022"
        )

    def test_teste_intermedio_nao_aceito(self):
        self._assert_invalid("Teste Intermédio, Português, 1.ª Fase, 2014")

    # — estrutura inválida —
    def test_vazio(self):
        self._assert_invalid("")

    def test_none(self):
        self._assert_invalid(None)  # type: ignore[arg-type]

    def test_ordem_trocada(self):
        self._assert_invalid("Português, Exame Nacional, 1.ª Fase, 2024")

    def test_ano_invalido(self):
        self._assert_invalid("Exame Nacional, Português, 1.ª Fase, 1999")

    def test_fase_invalida(self):
        self._assert_invalid("Exame Nacional, Português, 3.ª Fase, 2024")

    def test_lixo_extra(self):
        self._assert_invalid("Exame Nacional, Português, 1.ª Fase, 2024, extra")

    def test_materia_nao_canonica(self):
        self._assert_invalid("Exame Nacional, Física, 1.ª Fase, 2024")


class TestWhitelistsDeclaradas(unittest.TestCase):
    """Garante que a whitelist não é silenciosamente alargada."""

    def test_tipos_atuais(self):
        self.assertEqual(TIPOS_CANONICOS, frozenset({"Exame Nacional"}))

    def test_materias_atuais(self):
        self.assertEqual(MATERIAS_CANONICAS, frozenset({"Matemática A", "Português"}))

    def test_fases_atuais(self):
        self.assertEqual(
            FASES_CANONICAS,
            frozenset({"1.ª Fase", "2.ª Fase", "Época Especial"}),
        )


if __name__ == "__main__":
    unittest.main()
