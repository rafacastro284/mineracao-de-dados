#!/usr/bin/env python3
"""ETAPA 10 - Métricas de áudio e de fala, sem baixar os áudios de novo.

Entrada : cache/06_transcricoes*.jsonl            fim da última fala detectada pelo Whisper
          resultados/07_youtube_metricas.csv      duração do vídeo informada pela API
          resultados/09_transcricoes_normalizadas.csv   texto limpo, bloco e filtros de qualidade
Saída   : resultados/10_metricas_audio.csv        1 linha por vídeo transcrito

Por que sem os áudios: a etapa 6 apaga cada MP3 depois de transcrever, e baixar 284 h de
áudio de novo esbarra no bloqueio do YouTube. Métricas que dependem do sinal (SNR,
amplitude, zero-crossing rate, regiões de silêncio, como no notebook 18_audio_metrics do
lei_felca) ficaram de fora. As métricas abaixo saem da transcrição e da API.

Colunas:
  duracao_video_s        duração do vídeo pela API (etapa 7)
  fim_fala_s             fim do último trecho com fala segundo o Whisper (vazio = nenhuma fala)
  cobertura_fala         fim_fala_s / duracao_video_s, limitado a 1. É até onde vai a fala,
                         não a fração de tempo falado: um vídeo com fala só no começo e no
                         fim também dá 1. Valores baixos indicam fala só no início (intro de
                         música, trailer, gameplay)
  n_palavras             palavras do texto limpo (etapa 9)
  n_frases               frases do texto limpo
  palavras_por_frase     n_palavras / n_frases
  ppm_video              palavras por minuto de vídeo: densidade de fala no vídeo inteiro
  ppm_fala               palavras por minuto até o fim da fala: ritmo de quem fala
  ritmo                  sem_fala, esparsa (< 60 ppm de vídeo), moderada (60-120),
                         normal (120-180), rapida (> 180). Fala conversacional em inglês fica
                         em torno de 130-160 ppm; músicas e gameplay ficam abaixo de 60
  + bloco, title, idioma_original, traduzido, faixa_duracao, view_count, low_content,
    repeticao_alta, idioma_suspeito, base_recomendada

Atenção: os vídeos não ingleses passaram pela tradução do Whisper, então n_palavras e ppm são
das palavras em inglês, não da fala original. Compare ritmo de fala só entre vídeos em inglês.

Uso:
  python3 10_metricas_audio.py
"""
import glob
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent   # scripts/ -> videosDoReddit/
CACHE_DIR, RESULTADOS_DIR = HERE / "cache", HERE / "resultados"
METRICAS = RESULTADOS_DIR / "07_youtube_metricas.csv"
NORMALIZADAS = RESULTADOS_DIR / "09_transcricoes_normalizadas.csv"
SAIDA = RESULTADOS_DIR / "10_metricas_audio.csv"

FRASES = re.compile(r"(?<=[.!?])\s+")
FAIXAS_RITMO = [0, 60, 120, 180, np.inf]
NOMES_RITMO = ["esparsa", "moderada", "normal", "rapida"]


def carrega_fim_fala():
    """fim_fala_s do último registro de cada vídeo; um 'ok' não é substituído por erro (como na etapa 6)."""
    progresso = {}
    for caminho in sorted(glob.glob(str(CACHE_DIR / "06_transcricoes*.jsonl"))):
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                if linha.strip():
                    reg = json.loads(linha)
                    anterior = progresso.get(reg["video_id"])
                    if anterior is None or anterior["status"] != "ok" or reg["status"] == "ok":
                        progresso[reg["video_id"]] = reg
    return pd.DataFrame(
        [{"video_id": v, "fim_fala_s": r.get("duration_s")} for v, r in progresso.items() if r["status"] == "ok"]
    )


def main():
    norm = pd.read_csv(NORMALIZADAS, encoding="utf-8")
    api = pd.read_csv(METRICAS, encoding="utf-8").rename(columns={"duration_s": "duracao_video_s"})
    df = (norm.merge(carrega_fim_fala(), on="video_id", how="left")
              .merge(api[["video_id", "duracao_video_s", "faixa_duracao", "view_count"]], on="video_id", how="left"))

    texto = df["texto_limpo"].fillna("")
    df["n_palavras"] = texto.str.split().str.len()
    df["n_frases"] = texto.map(lambda t: len([f for f in FRASES.split(t) if f.strip()]))
    df["palavras_por_frase"] = (df["n_palavras"] / df["n_frases"]).where(df["n_frases"] > 0)

    duracao = df["duracao_video_s"].where(df["duracao_video_s"] > 0)
    fim = df["fim_fala_s"].where(df["fim_fala_s"] > 0)
    df["cobertura_fala"] = (fim / duracao).clip(upper=1)
    df["ppm_video"] = df["n_palavras"] / (duracao / 60)
    df["ppm_fala"] = df["n_palavras"] / (fim / 60)

    df["ritmo"] = pd.cut(df["ppm_video"], FAIXAS_RITMO, labels=NOMES_RITMO, right=False).astype(object)
    df.loc[df["n_palavras"] == 0, "ritmo"] = "sem_fala"
    df["base_recomendada"] = ~df["low_content"] & ~df["repeticao_alta"] & ~df["idioma_suspeito"]

    colunas = ["video_id", "bloco", "title", "idioma_original", "traduzido", "faixa_duracao", "view_count",
               "duracao_video_s", "fim_fala_s", "cobertura_fala", "n_palavras", "n_frases",
               "palavras_por_frase", "ppm_video", "ppm_fala", "ritmo",
               "low_content", "repeticao_alta", "idioma_suspeito", "base_recomendada"]
    df = df[colunas]
    df.round({"cobertura_fala": 3, "palavras_por_frase": 1, "ppm_video": 1, "ppm_fala": 1}).to_csv(
        SAIDA, index=False, encoding="utf-8")

    print(f"Pronto! {len(df)} vídeos -> {SAIDA.name}")
    base = df[df["base_recomendada"] & ~df["traduzido"]]
    print(f"\nBase recomendada em inglês original: {len(base)} vídeos. Mediana por bloco:")
    print(base.groupby("bloco")[["duracao_video_s", "cobertura_fala", "ppm_video", "ppm_fala",
                                 "palavras_por_frase"]].median().round(2).to_string())
    print("\nRitmo (todos os transcritos):\n" + df["ritmo"].value_counts().to_string())


if __name__ == "__main__":
    main()
