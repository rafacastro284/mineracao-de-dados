#!/usr/bin/env python3
"""
Resumo dos termos de busca da base -- TP1 Mineracao de Dados

Mostra, para cada termo de busca (coluna 'termo_busca'):
  - quantos videos ele trouxe
  - o idioma do termo
  - o periodo de PUBLICACAO desses videos (data mais antiga e mais recente)

IMPORTANTE: a base NAO registra o momento em que cada video foi COLETADO da
API (essa coluna nunca foi salva). Por isso a dimensao de tempo aqui e a data
de PUBLICACAO do video no YouTube ('publicado_em'), nao a da coleta.
Para registrar a data de coleta nas proximas rodadas, adicione uma coluna
'coletado_em' no coletor.

Rode de qualquer pasta:
    python3 resumo_termos.py
"""

from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent   # scripts/ -> raiz do projeto
PROC = RAIZ / "dados" / "processados" / "videos_limpos.csv"
BRUTO = RAIZ / "dados" / "brutos" / "videos_masculino.csv"
ENTRADA = PROC if PROC.exists() else BRUTO


def main():
    if not ENTRADA.exists():
        raise SystemExit(f"Nao encontrei a base ({ENTRADA}). Rode a coleta/limpeza antes.")

    df = pd.read_csv(ENTRADA, on_bad_lines="skip", engine="python")
    df["publicado_em"] = pd.to_datetime(df["publicado_em"], errors="coerce", utc=True)

    print(f"Base lida: {ENTRADA.name}  |  {len(df)} videos\n")

    # 1) termos de busca presentes + contagem + periodo de publicacao
    resumo = (
        df.groupby("termo_busca")
        .agg(
            idioma=("idioma_termo", "first"),
            videos=("video_id", "count"),
            publicado_de=("publicado_em", "min"),
            publicado_ate=("publicado_em", "max"),
        )
        .sort_values("videos", ascending=False)
    )
    resumo["publicado_de"] = resumo["publicado_de"].dt.date
    resumo["publicado_ate"] = resumo["publicado_ate"].dt.date

    print("== TERMOS DE BUSCA NA BASE (por nº de videos) ==")
    print(resumo.to_string())

    # 2) videos sem termo_busca (por ex. vindos de outra base no merge)
    sem_termo = df["termo_busca"].isna().sum()
    if sem_termo:
        print(f"\n(videos sem 'termo_busca' preenchido: {sem_termo})")

    # 3) distribuicao por ano de PUBLICACAO
    print("\n== VIDEOS POR ANO DE PUBLICACAO ==")
    por_ano = df["publicado_em"].dt.year.value_counts().sort_index()
    print(por_ano.to_string())

    # salva o resumo em CSV para o relatorio
    saida = RAIZ / "dados" / "processados" / "resumo_termos.csv"
    saida.parent.mkdir(parents=True, exist_ok=True)
    resumo.to_csv(saida)
    print(f"\nResumo salvo em: {saida}")


if __name__ == "__main__":
    main()