#!/usr/bin/env python3
"""ETAPA 7 - Coletar views, curtidas, nº de comentários e duração dos vídeos válidos.

Entrada : youtube_videos_validos.csv    (coluna video_id)
Saída   : 07_youtube_metricas.jsonl     cache de cada vídeo consultado (permite retomar sem gastar cota)
          07_youtube_metricas.csv       1 linha por vídeo, com as colunas abaixo

Colunas:
  retornado                            True se a API devolveu o vídeo; False = apagado/privado depois da etapa 3
  view_count, like_count, comment_count  vazios quando o canal oculta o dado ou desativou comentários
  duration_iso, duration_s             duração informada pela API (0 = live em andamento)
  faixa_duracao                        ate_60s, 1a3min, 3a20min, 20a60min, mais_60min
  live_broadcast                       none, live ou upcoming
  coletado_em                          as métricas valem para esta data

Observação: a API não informa se um vídeo é Short. 'faixa_duracao' é uma aproximação; o limite
de Shorts subiu de 60 s para 3 min em 2024, por isso as duas primeiras faixas são separadas.

Custo: 1 unidade de cota por lote de 50 (~42 unidades). Rodar de novo não gasta cota.

Uso:
  chave no .env de videosDoReddit/ (YT_API_KEY=... ou YOUTUBE_API_KEY=...)
  python3 07_metricas_videos.py
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent.parent   # scripts/ -> videosDoReddit/
ENTRADA_DIR, CACHE_DIR, RESULTADOS_DIR = HERE / "entrada", HERE / "cache", HERE / "resultados"
load_dotenv(HERE / ".env")

ENTRADA = ENTRADA_DIR / "youtube_videos_validos.csv"
CACHE = CACHE_DIR / "07_youtube_metricas.jsonl"
SAIDA = RESULTADOS_DIR / "07_youtube_metricas.csv"
API = "https://www.googleapis.com/youtube/v3"
RE_DURACAO = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def duracao_segundos(iso):
    m = RE_DURACAO.match(iso or "")
    if not m:
        return None
    dias, horas, minutos, segundos = (int(g or 0) for g in m.groups())
    return dias * 86400 + horas * 3600 + minutos * 60 + segundos


def faixa_duracao(segundos):
    if segundos is None or pd.isna(segundos) or segundos == 0:
        return None
    if segundos <= 60:
        return "ate_60s"
    if segundos <= 180:
        return "1a3min"
    if segundos <= 1200:
        return "3a20min"
    if segundos <= 3600:
        return "20a60min"
    return "mais_60min"


def busca_lote(ids, key):
    """Estatísticas e duração de até 50 vídeos por chamada."""
    for attempt in range(4):
        r = requests.get(f"{API}/videos", timeout=30,
                         params={"part": "statistics,contentDetails,snippet", "id": ",".join(ids), "key": key})
        if r.status_code == 200:
            return {it["id"]: it for it in r.json().get("items", [])}
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        sys.exit(f"Erro na API: HTTP {r.status_code}: {r.text[:200]}")
    sys.exit("API falhou após 4 tentativas")


def carrega_cache():
    cache = {}
    if CACHE.exists():
        with open(CACHE, encoding="utf-8") as f:
            for linha in f:
                if linha.strip():
                    reg = json.loads(linha)
                    cache[reg["video_id"]] = reg
    return cache


def main():
    video_ids = pd.read_csv(ENTRADA, encoding="utf-8-sig")["video_id"].astype(str).drop_duplicates().tolist()
    cache = carrega_cache()
    pendentes = [v for v in video_ids if v not in cache]
    print(f"{len(video_ids)} vídeos | {len(cache)} no cache | {len(pendentes)} a consultar")

    if pendentes:
        key = (os.environ.get("YOUTUBE_API_KEY") or os.environ.get("YT_API_KEY")
               or sys.exit("Defina YT_API_KEY (ou YOUTUBE_API_KEY) no .env de videosDoReddit/"))
        with open(CACHE, "a", encoding="utf-8") as f:
            for i in range(0, len(pendentes), 50):
                lote = pendentes[i:i + 50]
                itens = busca_lote(lote, key)
                agora = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                for video_id in lote:
                    it = itens.get(video_id)
                    stats = (it or {}).get("statistics", {})
                    reg = {
                        "video_id": video_id,
                        "retornado": it is not None,
                        "view_count": stats.get("viewCount"),
                        "like_count": stats.get("likeCount"),
                        "comment_count": stats.get("commentCount"),
                        "duration_iso": (it or {}).get("contentDetails", {}).get("duration"),
                        "live_broadcast": (it or {}).get("snippet", {}).get("liveBroadcastContent"),
                        "coletado_em": agora,
                    }
                    cache[video_id] = reg
                    f.write(json.dumps(reg, ensure_ascii=False) + "\n")
                f.flush()

    df = pd.DataFrame([cache[v] for v in video_ids])
    for col in ("view_count", "like_count", "comment_count"):
        df[col] = pd.to_numeric(df[col]).astype("Int64")
    df["duration_s"] = df["duration_iso"].map(duracao_segundos).astype("Int64")
    df["faixa_duracao"] = df["duration_s"].map(faixa_duracao)
    df.to_csv(SAIDA, index=False, encoding="utf-8")

    print(f"Retornados pela API: {int(df['retornado'].sum())} de {len(df)}")
    print(df["faixa_duracao"].value_counts().to_string())
    print(f"Saída: {SAIDA}")


if __name__ == "__main__":
    main()
