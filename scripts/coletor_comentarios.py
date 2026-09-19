#!/usr/bin/env python3
"""
Coletor de COMENTARIOS do YouTube -- TP1 Mineracao de Dados

Le a lista de videos ja coletada e puxa os comentarios de cada um.
Os caminhos sao calculados a partir da localizacao deste arquivo (scripts/),
entao voce pode rodar de qualquer pasta:
    python3 coletor_comentarios.py

Entrada: <raiz>/dados/brutos/videos_masculino.csv   (a lista de videos)
Saidas:  <raiz>/dados/brutos/comentarios.csv         (os comentarios)
         <raiz>/dados/brutos/comentarios_feitos.txt  (controle: videos ja processados)

Caracteristicas:
  - Pega os ~100 comentarios de topo (mais relevantes) por video.
  - Custo de cota: ~1 unidade por video -> muito barato (buscas custam 100).
  - RESUMIVEL: marca os videos ja processados; se rodar de novo (ou apos travar),
    continua de onde parou, sem repetir.
  - Se a cota da API esgotar, para com aviso SEM marcar os pendentes como feitos
    -> no dia seguinte ele retoma exatamente de onde parou.
  - Pula videos com comentarios desativados/removidos sem quebrar.

Observacao de privacidade (para o relatorio): comentarios sao conteudo de
usuarios e trazem o nome de exibicao do autor. Para a analise, considere
anonimizar/descartar a coluna 'autor'.
"""

import os
import csv
import json
from pathlib import Path
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_KEY = os.environ.get("YT_API_KEY")
if not API_KEY:
    raise SystemExit("Defina YT_API_KEY (via 'export' ou num arquivo .env).")

# --- Configuracao ---
RAIZ = Path(__file__).resolve().parent.parent   # scripts/ -> raiz do projeto
LISTA_VIDEOS = RAIZ / "dados" / "brutos" / "videos_masculino.csv"
SAIDA_COMENTARIOS = RAIZ / "dados" / "brutos" / "comentarios.csv"
CONTROLE = RAIZ / "dados" / "brutos" / "comentarios_feitos.txt"
MAX_COMENTARIOS_POR_VIDEO = 100      # ate ~100 comentarios de topo por video
ORDER = "relevance"                  # "relevance" (mais engajados) ou "time"

CAMPOS = ["comment_id", "video_id", "autor", "texto", "likes",
          "publicado_em", "respostas"]

youtube = build("youtube", "v3", developerKey=API_KEY)


def motivo_do_erro(e):
    """Extrai o 'reason' do erro da API (ex.: quotaExceeded, commentsDisabled)."""
    try:
        return json.loads(e.content)["error"]["errors"][0].get("reason", "")
    except Exception:
        return ""


def coletar_de_um_video(video_id):
    """Retorna (comentarios, status). status: 'ok' | 'indisponivel' | 'quota' | 'erro'."""
    linhas = []
    page_token = None
    while len(linhas) < MAX_COMENTARIOS_POR_VIDEO:
        try:
            resp = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=100,
                order=ORDER,
                textFormat="plainText",
                pageToken=page_token,
            ).execute()
        except HttpError as e:
            motivo = motivo_do_erro(e)
            status = getattr(e.resp, "status", None)
            if motivo in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
                return linhas, "quota"            # cota acabou -> nao marcar como feito
            if motivo == "commentsDisabled" or status == 404:
                return linhas, "indisponivel"     # sem comentarios / video removido
            return linhas, "erro"                 # transitorio -> tentar de novo depois
        for item in resp.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            linhas.append({
                "comment_id": item["snippet"]["topLevelComment"]["id"],
                "video_id": video_id,
                "autor": top.get("authorDisplayName"),
                "texto": top.get("textOriginal"),
                "likes": top.get("likeCount"),
                "publicado_em": top.get("publishedAt"),
                "respostas": item["snippet"].get("totalReplyCount"),
            })
            if len(linhas) >= MAX_COMENTARIOS_POR_VIDEO:
                break
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return linhas, "ok"


def carregar_feitos():
    if CONTROLE.exists():
        return set(CONTROLE.read_text(encoding="utf-8").split())
    return set()


def main():
    if not LISTA_VIDEOS.exists():
        raise SystemExit(f"Nao encontrei {LISTA_VIDEOS}. Rode o coletor de videos antes.")

    videos = pd.read_csv(LISTA_VIDEOS)["video_id"].astype(str).tolist()
    feitos = carregar_feitos()
    pendentes = [v for v in videos if v not in feitos]
    print(f"Videos na base: {len(videos)} | ja processados: {len(feitos)} | "
          f"a processar agora: {len(pendentes)}")

    SAIDA_COMENTARIOS.parent.mkdir(parents=True, exist_ok=True)
    novo_arquivo = not SAIDA_COMENTARIOS.exists()

    total_coment = 0
    sem_comentarios = 0
    with open(SAIDA_COMENTARIOS, "a", newline="", encoding="utf-8") as fcsv, \
         open(CONTROLE, "a", encoding="utf-8") as fctrl:
        writer = csv.DictWriter(fcsv, fieldnames=CAMPOS, quoting=csv.QUOTE_ALL)
        if novo_arquivo:
            writer.writeheader()

        for i, vid in enumerate(pendentes, 1):
            linhas, status = coletar_de_um_video(vid)

            if status == "quota":
                print("Cota da API esgotada -- parando aqui SEM marcar os pendentes.")
                print("Rode de novo amanha (apos o reset da cota) que ele retoma daqui.")
                break
            if status == "erro":
                continue   # erro transitorio: nao grava nem marca -> tenta na proxima

            # status 'ok' ou 'indisponivel': grava o que veio e marca como feito
            for linha in linhas:
                writer.writerow(linha)
            total_coment += len(linhas)
            if status == "indisponivel":
                sem_comentarios += 1
            fcsv.flush()
            fctrl.write(vid + "\n")
            fctrl.flush()

            if i % 25 == 0:
                print(f"  ... {i}/{len(pendentes)} videos | {total_coment} comentarios")

    print(f"Pronto! Coletados {total_coment} comentarios nesta rodada.")
    print(f"Videos sem comentarios/desativados: {sem_comentarios}")
    print(f"Arquivo: {SAIDA_COMENTARIOS}")


if __name__ == "__main__":
    main()