#!/usr/bin/env python3
"""
Coletor de metadados do YouTube (v2) -- TP1 Mineracao de Dados
Tema: da onda de cuidado/estetica masculina ate a ideologia (looksmaxxing, manosphere)

NOVIDADES desta versao:
  - ACUMULA: le o CSV que ja existe, ignora videos repetidos e so adiciona os
    novos. Pode rodar varias vezes (ate em dias diferentes) que a base cresce.
  - Opcao ORDER: rode com "relevance" hoje, "viewCount" e "date" em outros dias
    para pescar videos diferentes com os mesmos termos.
  - (AJUSTE - ponto 8) PUBLISHED_AFTER / PUBLISHED_BEFORE: filtro opcional de
    data de publicacao, para quem quiser restringir o recorte temporal da
    coleta (ex.: so videos publicados a partir de 2023). Deixe None em ambos
    para manter o comportamento antigo (sem filtro de data).

Como usar (de dentro da pasta scripts/):
    python3 coletor_youtube.py

Chave da API: lida da variavel de ambiente YT_API_KEY, ou de um arquivo .env
(YT_API_KEY=...) na mesma pasta, se voce tiver instalado o python-dotenv.

Cota (limite padrao 10.000 unidades/dia): cada busca custa 100 unidades.
Se quiser mais, rode de novo amanha mudando o ORDER (a base acumula).

Observacao: a busca do YouTube NAO diferencia maiuscula de minuscula
('Alpha male' == 'alpha male'), entao nao vale duplicar termos so pela caixa.

Para COMENTAR uma linha, use # no comeco dela (nao use aspas triplas '''):
    # ("termo que nao quero agora", "pt"),
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
# Cada item e ("termo", "idioma"). A busca ignora maiuscula/minuscula.
SEARCH_TERMS = [
    # ---- Portugues (criadores) ----
    ("Rain santos", "pt"),
    ("Thiago nigro", "pt"),
    ("Gabriel breier", "pt"),
    ("Breno faria", "pt"),
    # ---- Ingles (glossario / masculinidade) ----
    ("High-value man", "en"),
    ("Male supremacism", "en"),
    ("AWALT", "en"),
    ("Alpha male", "en"),
]

MAX_PAGES_PER_TERM = 6          # 6 paginas x 50 = ate ~300 videos por termo
RESULTS_PER_PAGE = 50           # maximo da API
ORDER = "relevance"             # "relevance" | "viewCount" | "date" | "rating"

# (AJUSTE - ponto 8) filtro opcional de recorte temporal da coleta.
# Formato RFC 3339 (obrigatorio "Z" no final, meia-noite UTC).
# Deixe None para nao filtrar por data (comportamento antigo).
#   PUBLISHED_AFTER = "2023-01-01T00:00:00Z"
#   PUBLISHED_BEFORE = "2026-01-01T00:00:00Z"
PUBLISHED_AFTER = None
PUBLISHED_BEFORE = None

RAIZ = Path(__file__).resolve().parent.parent   # scripts/ -> raiz do projeto
OUTPUT_CSV = RAIZ / "dados" / "brutos" / "videos_masculino.csv"

youtube = build("youtube", "v3", developerKey=API_KEY)


def buscar_ids(termo, idioma):
    """Retorna lista de video_ids de um termo, paginando ate MAX_PAGES_PER_TERM."""
    ids = []
    page_token = None
    for _ in range(MAX_PAGES_PER_TERM):
        # (AJUSTE - ponto 8) monta os kwargs da busca, so incluindo os filtros
        # de data quando eles estiverem configurados acima.
        kwargs = dict(
            q=termo,
            part="id",
            type="video",
            maxResults=RESULTS_PER_PAGE,
            order=ORDER,
            pageToken=page_token,
            relevanceLanguage=idioma,
        )
        if PUBLISHED_AFTER:
            kwargs["publishedAfter"] = PUBLISHED_AFTER
        if PUBLISHED_BEFORE:
            kwargs["publishedBefore"] = PUBLISHED_BEFORE

        try:
            resp = youtube.search().list(**kwargs).execute()
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
    if PUBLISHED_AFTER or PUBLISHED_BEFORE:
        print(f"Filtro de data ativo: publishedAfter={PUBLISHED_AFTER}  "
              f"publishedBefore={PUBLISHED_BEFORE}")

    # 1) carrega o que ja existe (ignorando linhas eventualmente corrompidas)
    if OUTPUT_CSV.exists():
        base = pd.read_csv(OUTPUT_CSV, on_bad_lines="skip", engine="python")
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