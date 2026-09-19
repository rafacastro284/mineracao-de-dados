#!/usr/bin/env python3
"""
Limpeza / pre-processamento da base coletada do YouTube -- TP1 Mineracao de Dados

Le o dado BRUTO e salva uma COPIA limpa, sem nunca alterar o original.
Os caminhos sao calculados a partir da localizacao deste arquivo (scripts/),
entao voce pode rodar de qualquer pasta:
    python3 limpeza.py

Entrada:  <raiz do projeto>/dados/brutos/videos_masculino.csv
Saida:    <raiz do projeto>/dados/processados/videos_limpos.csv

O que faz (e por que):
  - Normaliza o texto para a forma canonica NFC (mesma letra acentuada
    representada sempre do mesmo jeito -> evita "duplicatas" de texto).
  - Remove SO caracteres invisiveis orfaos (BOM, espaco zero-width solto,
    marcadores de direcao). MANTEM o ZWJ/ZWNJ, que fazem parte de emojis
    compostos (ex.: pessoa + sinal = um emoji so) -> preserva informacao.
  - Padroniza espacos em branco.
  - Converte a data de publicacao para datetime e cria a coluna 'ano'.
  - Converte a duracao ISO-8601 (ex.: PT10M30S) para segundos ('duracao_seg').
  - Respeita os vazios legitimos (descricao/tags nao preenchidas, likes
    ocultos) -- nao inventa dado.
"""

import re
import unicodedata
from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent   # scripts/ -> raiz do projeto
ENTRADA = RAIZ / "dados" / "brutos" / "videos_masculino.csv"
SAIDA = RAIZ / "dados" / "processados" / "videos_limpos.csv"

COLS_TEXTO = ["titulo", "descricao", "canal", "tags"]

# Invisiveis que sao LIXO real (remover):
LIXO_INVISIVEL = ["\u200b", "\ufeff", "\u2060", "\u200e", "\u200f"]
# NAO removemos \u200d (ZWJ) nem \u200c (ZWNJ): participam de emojis e de
# sistemas de escrita complexos.


def limpa_texto(s):
    if pd.isna(s):
        return s
    s = unicodedata.normalize("NFC", str(s))
    for ch in LIXO_INVISIVEL:
        s = s.replace(ch, "")
    s = s.replace("\u00a0", " ")        # espaco nao-quebravel -> espaco normal
    s = re.sub(r"\s+", " ", s).strip()  # colapsa espacos e remove das pontas
    return s


def duracao_para_segundos(iso):
    """Converte duracao ISO-8601 (PT#H#M#S) em segundos. Retorna None se nao casar."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", str(iso))
    if not m:
        return None
    h, mi, se = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + se


def main():
    df = pd.read_csv(ENTRADA, on_bad_lines='skip', engine='python')
    n_inicial = len(df)

    for c in COLS_TEXTO:
        if c in df.columns:
            df[c] = df[c].apply(limpa_texto)

    df["publicado_em"] = pd.to_datetime(df["publicado_em"], errors="coerce", utc=True)
    df["ano"] = df["publicado_em"].dt.year
    df["duracao_seg"] = df["duracao_iso"].apply(duracao_para_segundos)

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SAIDA, index=False)

    print(f"Base bruta:   {n_inicial} videos")
    print(f"Base limpa:   {len(df)} videos  ->  {SAIDA}")
    print(f"Colunas: {list(df.columns)}")


if __name__ == "__main__":
    main()