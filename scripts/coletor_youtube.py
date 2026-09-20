#!/usr/bin/env python3
"""
Coletor de metadados do YouTube (v2) -- TP1 Mineracao de Dados
Tema: nova onda de cuidado/embelezamento masculino (skincare, grooming, looksmaxxing)

NOVIDADES desta versao:
  - ACUMULA: le o CSV que ja existe, ignora videos repetidos e so adiciona os
    novos. Pode rodar varias vezes (ate em dias diferentes) que a base cresce.
  - Mais termos de busca e mais paginas por termo.
  - Opcao ORDER: rode com "relevance" hoje, "viewCount" e "date" em outros dias
    para pescar videos diferentes com os mesmos termos.

Como usar (de dentro da pasta scripts/):
    python3 coletor_youtube.py

Chave da API: lida da variavel de ambiente YT_API_KEY, ou de um arquivo .env
(YT_API_KEY=...) na mesma pasta, se voce tiver instalado o python-dotenv.

Cota (limite padrao 10.000 unidades/dia): cada busca custa 100 unidades.
Com ~21 termos x 4 paginas = ~84 buscas = ~8.400 unidades -> cabe num dia.
Se quiser mais, rode de novo amanha mudando o ORDER (a base acumula).
"""

import os
import csv
import time
from pathlib import Path
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# .env e opcional: se o python-dotenv estiver instalado, carrega a chave dele
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_KEY = os.environ.get("YT_API_KEY")
if not API_KEY:
    raise SystemExit("Defina YT_API_KEY (via 'export' ou num arquivo .env).")

# --- Configuracao da coleta ---
SEARCH_TERMS = [
    # ---- Portugues ----
    ("Rain Santos", "pt"),
    ("Thiago Nigro", "pt"),
    ("Gabriel Breier", "pt"),
    ("Breno Faria", "pt"),
]

MAX_PAGES_PER_TERM = 4          # 4 paginas x 50 = ate ~200 videos por termo
RESULTS_PER_PAGE = 50           # maximo da API
ORDER = "date"             # "relevance" | "viewCount" | "date" | "rating"
RAIZ = Path(__file__).resolve().parent.parent   # scripts/ -> raiz do projeto
OUTPUT_CSV = RAIZ / "dados" / "brutos" / "videos_masculino.csv"

youtube = build("youtube", "v3", developerKey=API_KEY)


def buscar_ids(termo, idioma):
    """Retorna lista de video_ids de um termo, paginando ate MAX_PAGES_PER_TERM."""
    ids = []
    page_token = None
    for _ in range(MAX_PAGES_PER_TERM):
        try:
            resp = youtube.search().list(
                q=termo,
                part="id",
                type="video",
                maxResults=RESULTS_PER_PAGE,
                order=ORDER,
                pageToken=page_token,
                relevanceLanguage=idioma,
            ).execute()
        except HttpError as e:
            print(f"  ! Erro na busca por '{termo}': {e}")
            break
        for item in resp.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid:
                ids.append(vid)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids


def detalhes_videos(video_ids):
    """Busca metadados completos em lotes de 50 IDs."""
    linhas = []
    for i in range(0, len(video_ids), 50):
        lote = video_ids[i:i + 50]
        try:
            resp = youtube.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(lote),
            ).execute()
        except HttpError as e:
            print(f"  ! Erro ao buscar detalhes: {e}")
            continue
        for item in resp.get("items", []):
            snip = item.get("snippet", {})
            stats = item.get("statistics", {})
            cont = item.get("contentDetails", {})
            linhas.append({
                "video_id": item.get("id"),
                "titulo": snip.get("title"),
                "descricao": snip.get("description"),
                "canal": snip.get("channelTitle"),
                "publicado_em": snip.get("publishedAt"),
                "categoria_id": snip.get("categoryId"),
                "idioma_video": snip.get("defaultAudioLanguage") or snip.get("defaultLanguage"),
                "tags": "|".join(snip.get("tags", [])),
                "duracao_iso": cont.get("duration"),
                "views": stats.get("viewCount"),
                "likes": stats.get("likeCount"),
                "comentarios": stats.get("commentCount"),
            })
    return linhas


def main():
    # 1) carrega o que ja existe (com on_bad_lines para ignorar linhas corrompidas anteriores)
    if OUTPUT_CSV.exists():
        try:
            base = pd.read_csv(OUTPUT_CSV, on_bad_lines='skip', engine='python')
        except Exception:
            base = pd.read_csv(OUTPUT_CSV, error_bad_lines=False, engine='python') # Compatibilidade extra
            
        ja_tem = set(base["video_id"].astype(str))
        print(f"Base atual: {len(base)} videos ja coletados.")
    else:
        base = pd.DataFrame()
        ja_tem = set()
        print("Nenhuma base anterior encontrada -- comecando do zero.")

    # 2) busca IDs e fica so com os novos
    print(f"Buscando IDs (order={ORDER})...")
    novos = {}   # video_id -> (termo, idioma)
    for termo, idioma in SEARCH_TERMS:
        print(f"  - [{idioma}] {termo}")
        for vid in buscar_ids(termo, idioma):
            if vid not in ja_tem and vid not in novos:
                novos[vid] = (termo, idioma)
        time.sleep(0.2)
    print(f"Videos NOVOS encontrados: {len(novos)}")

    if not novos:
        print("Nada novo para adicionar. Tente outro ORDER ou novos termos.")
        return

    # 3) detalhes so dos novos
    print("Buscando metadados dos novos...")
    linhas = detalhes_videos(list(novos.keys()))
    for linha in linhas:
        termo, idioma = novos.get(linha["video_id"], ("", ""))
        linha["termo_busca"] = termo
        linha["idioma_termo"] = idioma
    novos_df = pd.DataFrame(linhas)

    # 4) junta com a base antiga e salva
    final = pd.concat([base, novos_df], ignore_index=True)
    final = final.drop_duplicates(subset="video_id", keep="first")
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    final.to_csv(OUTPUT_CSV, index=False, quoting=csv.QUOTE_ALL)
    print(f"Adicionados {len(novos_df)} videos. Base agora: {len(final)} -> {OUTPUT_CSV}")


if __name__ == "__main__":
    main()