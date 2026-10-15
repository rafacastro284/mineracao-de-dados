#!/usr/bin/env python3
"""ETAPA 4 - Classificar os vídeos válidos em categoria e conteúdo.

Entrada : youtube_videos_validos.csv   (1 linha por vídeo, sem duplicados)
Saída   : youtube_videos_classificados.csv
          youtube_videos_PARA_REVISAR.csv  planilha para a revisão manual (ver abaixo)
          04_youtube_detalhes.jsonl    cache de descrição/tags vindas da API (permite retomar)

O que faz:
  1) categoria: nome legível a partir do category_id do YouTube (mesma tabela do
     scripts/classifica_blocos.py do projeto).
  2) busca descrição e tags de cada vídeo na API (lotes de 50 = 1 unidade de cota cada;
     ~42 chamadas para ~2.100 vídeos). Fica em cache: rodar de novo não gasta cota.
  3) conteudo: classificação zero-shot por similaridade de embeddings. O texto do vídeo
     (título + tags + início da descrição) é comparado com as frases de exemplo de cada
     tema em TEMAS (vale a frase mais parecida). Se o tema combina com a categoria que o
     próprio YouTube deu ao vídeo (CATEGORIA_TEMAS), ganha BONUS_CATEGORIA. O vídeo recebe
     o tema de maior pontuação; abaixo de LIMIAR vira "outros".
     Modelo: o mesmo do BERTopic do projeto.

Colunas novas:
  categoria          nome da categoria do YouTube
  conteudo           tema mais provável (ou "outros")
  conteudo_score     pontuação do tema escolhido (similaridade + bônus; maior = mais confiável)
  conteudo_2         segundo tema mais provável (ajuda a revisar casos ambíguos)
  conteudo_manual    sua correção, vinda da planilha de revisão (vazio = não corrigido)
  revisado           True se a linha foi revisada à mão
  conteudo_final     conteudo_manual se preenchido, senão conteudo -> use esta na análise
  tags, descricao    vindos da API (descrição cortada em 500 caracteres)
  retornado          True se a API devolveu o vídeo; False = apagado/privado depois da
                     etapa 3 -> descrição/tags vazias aqui significam "desconhecido",
                     não "vídeo sem descrição" (trate como desconhecido nas etapas seguintes)
  amostra            True para os vídeos da amostra aleatória de validação (ver abaixo)

Revisão manual (RODE ESTE SCRIPT DUAS VEZES, como no scripts/bertopics.py):
  - 1a vez: gera youtube_videos_PARA_REVISAR.csv, com a coluna 'conteudo_manual' vazia,
    ordenada por prioridade (0 = amostra aleatória de validação, 1 = temas centrais do
    projeto, 2 = baixa confiança, 3 = resto).
  - AMOSTRA (prioridade 0): TAMANHO_AMOSTRA vídeos sorteados (SEMENTE fixa) entre todos.
    Revise TODAS essas linhas e marque 'revisado' com x em cada uma (inclusive as certas):
    é delas que sai a taxa de acerto para o artigo. As demais prioridades foram escolhidas
    a dedo (temas centrais, baixa confiança), então o acerto nelas é enviesado e serve só
    como diagnóstico.
  - Abra no Excel/Sheets e preencha 'conteudo_manual' só onde o automático errou, com um
    dos nomes de TEMAS ou "outros" (vazio = o automático está certo). Salve por cima,
    mesmo nome, formato CSV.
  - 2a vez: o script lê a planilha e cria 'conteudo_final' (manual se preenchido, senão o
    automático) e mostra o acerto do automático na amostra aleatória (com intervalo de
    confiança de 95%) e, à parte, nas demais linhas revisadas. A planilha nunca é
    sobrescrita; para gerar uma nova do zero, apague-a.

Para ajustar: edite TEMAS, CATEGORIA_TEMAS, LIMIAR ou BONUS_CATEGORIA e rode de novo
(a parte da API fica em cache, então só a classificação é refeita).

Uso:
  chave no .env da pasta (YT_API_KEY=... ou YOUTUBE_API_KEY=...)
  python3 04_classifica_videos.py
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

ENTRADA = HERE / "youtube_videos_validos.csv"
SAIDA = HERE / "youtube_videos_classificados.csv"
CACHE = HERE / "04_youtube_detalhes.jsonl"
REVISAO = HERE / "youtube_videos_PARA_REVISAR.csv"
API = "https://www.googleapis.com/youtube/v3"

MODELO_EMBEDDING = "paraphrase-multilingual-MiniLM-L12-v2"
LIMIAR = 0.30           # pontuação mínima; abaixo disso o vídeo vai para "outros"
BONUS_CATEGORIA = 0.10  # soma à similaridade quando o tema combina com a categoria do YouTube
TAMANHO_AMOSTRA = 200   # vídeos sorteados para medir o acerto sem viés
SEMENTE = 42            # fixa: o sorteio é sempre o mesmo

# categorias oficiais do YouTube (id -> nome legível)
CATEGORIAS_YT = {
    1: "Filme e Animacao", 2: "Automoveis", 10: "Musica", 15: "Animais e Pets",
    17: "Esporte", 18: "Curtas", 19: "Viagem e Eventos", 20: "Jogos",
    21: "Videoblog", 22: "Pessoas e Blogs", 23: "Comedia", 24: "Entretenimento",
    25: "Noticias e Politica", 26: "Moda e Estilo", 27: "Educacao",
    28: "Ciencia e Tecnologia", 29: "ONGs e Ativismo", 30: "Filmes",
    43: "Programas", 44: "Trailers",
}

# tema -> frases de exemplo (em inglês: a maioria dos vídeos do Reddit é EN; o modelo é
# multilíngue, então vídeos em PT também casam). Vale a frase mais parecida com o vídeo.
TEMAS = {
    "autocuidado/estetica": [
        "men's skincare routine", "grooming tips for men, beard and haircut",
        "hair loss treatment, minoxidil, hair transplant", "men's fashion and style advice"],
    "looksmaxxing": [
        "looksmaxxing guide", "mewing for a better jawline", "how to become more attractive, facial aesthetics",
        "subliminal for a beautiful face"],
    "manosphere/ideologia": [
        "red pill truth about women", "alpha male mindset, high value man", "Andrew Tate on masculinity",
        "men's rights and feminism debate", "modern women and hypergamy", "incels and the dating market"],
    "relacionamentos/seducao": [
        "dating advice for men", "how to attract women", "relationship and marriage advice",
        "breakup and divorce"],
    "fitness/corpo": [
        "gym workout routine", "bodybuilding and muscle growth", "diet, nutrition and supplements",
        "home exercise to lose weight"],
    "desenvolvimento_pessoal": [
        "self improvement and discipline", "motivational speech", "productivity habits",
        "stoicism and mindset", "book summary and life lessons"],
    "saude/sexualidade": [
        "men's health and testosterone", "mental health, depression and therapy", "sexual health, erectile dysfunction",
        "semen retention and nofap", "medical doctor explains disease"],
    "politica/noticias": [
        "political commentary on Trump and Biden", "news report", "election and government",
        "war, Israel and Palestine, geopolitics", "president speech", "left vs right debate"],
    "religiao/filosofia": [
        "christian sermon, faith in God", "islam and the quran", "philosophy lecture",
        "atheism and religion debate", "leaving a religion, ex mormon, Jehovah's Witnesses"],
    "games": [
        "video game trailer", "gameplay walkthrough", "game review", "game mod showcase",
        "esports tournament", "PC build and graphics card"],
    "musica": [
        "official music video", "song lyrics", "live concert performance", "k-pop idol group",
        "rap and hip hop album", "metal band"],
    "cinema/tv/cultura_pop": [
        "movie scene clip", "film trailer", "tv show episode", "anime", "celebrity gossip", "vtuber stream"],
    "humor/entretenimento": [
        "funny comedy sketch", "stand-up comedy", "podcast episode", "reaction video", "memes compilation"],
    "ciencia/tecnologia": [
        "science explained", "technology review", "artificial intelligence", "space and astronomy",
        "UFO and aliens documentary", "history documentary"],
    "economia/financas": [
        "investing in stocks", "cryptocurrency and bitcoin", "personal finance and taxes", "economy explained"],
    "esporte": [
        "football highlights", "basketball NBA", "pro wrestling", "MMA and boxing fight", "cricket match"],
    "culinaria": [
        "cooking recipe", "how to cook food", "restaurant and street food"],
}

# categoria do YouTube -> temas que combinam com ela (recebem BONUS_CATEGORIA)
CATEGORIA_TEMAS = {
    "Musica": ["musica"],
    "Jogos": ["games"],
    "Esporte": ["esporte", "fitness/corpo"],
    "Noticias e Politica": ["politica/noticias", "manosphere/ideologia"],
    "Filme e Animacao": ["cinema/tv/cultura_pop"],
    "Comedia": ["humor/entretenimento"],
    "Entretenimento": ["humor/entretenimento", "cinema/tv/cultura_pop"],
    "Moda e Estilo": ["autocuidado/estetica", "looksmaxxing", "culinaria"],
    "Ciencia e Tecnologia": ["ciencia/tecnologia"],
    "Educacao": ["ciencia/tecnologia", "desenvolvimento_pessoal", "economia/financas"],
    "ONGs e Ativismo": ["politica/noticias"],
}


# ---------------------------------------------------------------- API
def busca_detalhes(ids, key):
    """Descrição e tags de até 50 vídeos por chamada."""
    for attempt in range(4):
        r = requests.get(f"{API}/videos", timeout=30,
                         params={"part": "snippet", "id": ",".join(ids), "key": key})
        if r.status_code == 200:
            return {it["id"]: it["snippet"] for it in r.json().get("items", [])}
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        sys.exit(f"Erro na API: HTTP {r.status_code}: {r.text[:200]}")
    sys.exit("API falhou após 4 tentativas")


def carrega_detalhes(video_ids):
    cache = {}
    if CACHE.exists():
        with open(CACHE, encoding="utf-8") as f:
            cache = {r["video_id"]: r for r in map(json.loads, f)}
    # registros antigos, sem 'retornado', são buscados de novo (não dá para saber se a API
    # devolveu o vídeo); a versão nova vai para o fim do arquivo e prevalece na leitura
    faltam = [v for v in video_ids if "retornado" not in cache.get(v, {})]
    print(f"detalhes: {len(cache)} no cache | a buscar: {len(faltam)}")
    if faltam:
        key = (os.environ.get("YOUTUBE_API_KEY") or os.environ.get("YT_API_KEY")
               or sys.exit("Defina YT_API_KEY (ou YOUTUBE_API_KEY) no .env da pasta"))
        with open(CACHE, "a", encoding="utf-8") as f:
            for i in range(0, len(faltam), 50):
                lote = faltam[i:i + 50]
                achados = busca_detalhes(lote, key)
                for v in lote:
                    sn = achados.get(v, {})
                    rec = {"video_id": v, "retornado": v in achados,
                           "descricao": sn.get("description", ""), "tags": sn.get("tags", [])}
                    cache[v] = rec
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(f"  {min(i + 50, len(faltam))}/{len(faltam)}", end="\r")
        print()
    return cache


# ---------------------------------------------------------------- classificação
def classifica_conteudo(textos, categorias):
    modelo = SentenceTransformer(MODELO_EMBEDDING)
    nomes = list(TEMAS)
    emb_videos = modelo.encode(textos, normalize_embeddings=True, batch_size=64,
                               show_progress_bar=True)
    # similaridade de cosseno com cada frase; por tema vale a maior
    sims = np.column_stack([
        (emb_videos @ modelo.encode(frases, normalize_embeddings=True).T).max(axis=1)
        for frases in TEMAS.values()])
    bonus = np.array([[BONUS_CATEGORIA if t in CATEGORIA_TEMAS.get(c, ()) else 0.0
                       for t in nomes] for c in categorias])
    pont = sims + bonus
    ordem = pont.argsort(axis=1)[:, ::-1]
    score = pont[np.arange(len(textos)), ordem[:, 0]]
    conteudo = [nomes[o[0]] if s >= LIMIAR else "outros" for o, s in zip(ordem, score)]
    segundo = [nomes[o[1]] for o in ordem]
    return conteudo, score.round(3), segundo


# ---------------------------------------------------------------- revisão manual
TEMAS_CENTRAIS = {"autocuidado/estetica", "looksmaxxing", "manosphere/ideologia",
                  "relacionamentos/seducao", "fitness/corpo", "desenvolvimento_pessoal",
                  "saude/sexualidade"}
COLS_REVISAO = ["prioridade", "amostra", "video_id", "url", "title", "channel_title", "categoria",
                "tags", "descricao", "conteudo", "conteudo_2", "conteudo_score",
                "conteudo_manual", "revisado"]


def gera_planilha_revisao(df):
    rev = df.copy()
    central = rev["conteudo"].isin(TEMAS_CENTRAIS) | rev["conteudo_2"].isin(TEMAS_CENTRAIS)
    rev["prioridade"] = np.where(central, 1, np.where(rev["conteudo_score"] < 0.40, 2, 3))
    rev.loc[rev["amostra"], "prioridade"] = 0
    rev["tags"] = rev["tags"].str[:150]
    rev["descricao"] = rev["descricao"].str[:200].str.replace(r"\s+", " ", regex=True)
    rev["conteudo_manual"] = ""
    rev["revisado"] = ""
    rev = rev.sort_values(["prioridade", "conteudo", "conteudo_score"])
    rev[COLS_REVISAO].to_csv(REVISAO, index=False, encoding="utf-8-sig")
    print(f"\nplanilha de revisão criada: {REVISAO.name}")
    print(rev["prioridade"].value_counts().sort_index().rename("vídeos por prioridade").to_string())


def aplica_revisao(df):
    """Junta a revisão manual. 'revisado' marcado (x/sim/1) ou conteudo_manual preenchido
    contam como linha revisada; vazio em conteudo_manual = o automático estava certo."""
    rev = pd.read_csv(REVISAO, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    rev["conteudo_manual"] = rev["conteudo_manual"].str.strip().str.lower()
    marcado = rev["revisado"].str.strip().str.lower().isin({"x", "sim", "s", "1", "true", "ok"})
    rev["revisado"] = marcado | (rev["conteudo_manual"] != "")

    validos = set(TEMAS) | {"outros"}
    invalidos = rev[(rev["conteudo_manual"] != "") & ~rev["conteudo_manual"].isin(validos)]
    if len(invalidos):
        print(f"\nAVISO: {len(invalidos)} valores de conteudo_manual não são temas válidos "
              "(ignorados):")
        print(invalidos[["video_id", "title", "conteudo_manual"]].head(20).to_string(index=False))
        rev.loc[invalidos.index, "conteudo_manual"] = ""

    rev = rev.set_index("video_id")
    df["conteudo_manual"] = df["video_id"].map(rev["conteudo_manual"]).fillna("")
    df["revisado"] = df["video_id"].map(rev["revisado"]).fillna(False).astype(bool)
    df["conteudo_final"] = df["conteudo_manual"].where(df["conteudo_manual"] != "", df["conteudo"])

    r = df[df["revisado"]]
    print(f"\n--- revisão manual: {len(r)} vídeos revisados, "
          f"{(r['conteudo_manual'] != '').sum()} corrigidos ---")

    # acerto para o artigo: só a amostra aleatória (as outras linhas foram escolhidas a dedo)
    a = df[df["amostra"]]
    ra = a[a["revisado"]]
    if len(ra):
        p = (ra["conteudo_final"] == ra["conteudo"]).mean()
        lo, hi = wilson(p, len(ra))
        print(f"acerto do automático na AMOSTRA ALEATÓRIA: {p:.1%} "
              f"(IC 95% {lo:.1%}-{hi:.1%}, n={len(ra)})")
        if len(ra) < len(a):
            print(f"  AVISO: {len(a) - len(ra)} linhas da amostra ainda sem 'revisado' marcado; "
                  "revise todas para o número valer para o conjunto inteiro")
    resto = r[~r["amostra"]]
    if len(resto):
        p = (resto["conteudo_final"] == resto["conteudo"]).mean()
        print(f"acerto nas demais linhas revisadas (enviesado, só diagnóstico): {p:.1%} "
              f"(n={len(resto)})")
    return df


def wilson(p, n, z=1.96):
    """Intervalo de confiança de Wilson para uma proporção."""
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    margem = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centro - margem, centro + margem


# ---------------------------------------------------------------- main
def main():
    df = pd.read_csv(ENTRADA, encoding="utf-8-sig", dtype={"category_id": "Int64"})
    print(f"=== Etapa 4: classificação de {len(df)} vídeos ===")

    df["categoria"] = df["category_id"].map(
        lambda c: "Desconhecida" if pd.isna(c) else CATEGORIAS_YT.get(int(c), f"Outra (id {c})"))

    det = carrega_detalhes(df["video_id"].tolist())
    df["tags"] = df["video_id"].map(lambda v: ";".join(det[v]["tags"]))
    df["descricao"] = df["video_id"].map(lambda v: det[v]["descricao"][:500])
    df["retornado"] = df["video_id"].map(lambda v: det[v]["retornado"])
    n_fora = (~df["retornado"]).sum()
    if n_fora:
        print(f"AVISO: {n_fora} vídeos não foram devolvidos pela API (apagados/privados): "
              "classificados só pelo título; descrição/tags = desconhecido")
    df["amostra"] = df.index.isin(
        df.sample(n=min(TAMANHO_AMOSTRA, len(df)), random_state=SEMENTE).index)

    textos = (df["title"].fillna("") + ". " + df["tags"].str.replace(";", ", ")
              + ". " + df["descricao"].str[:300]).tolist()
    df["conteudo"], df["conteudo_score"], df["conteudo_2"] = classifica_conteudo(textos, df["categoria"])

    if REVISAO.exists():
        df = aplica_revisao(df)
    else:
        gera_planilha_revisao(df)
        df["conteudo_manual"], df["revisado"], df["conteudo_final"] = "", False, df["conteudo"]

    cols_ini = ["video_id", "url", "title", "channel_title", "categoria", "conteudo_final",
                "conteudo", "conteudo_score", "conteudo_2", "conteudo_manual", "revisado",
                "amostra", "retornado"]
    df = df[cols_ini + [c for c in df.columns if c not in cols_ini]]
    df.to_csv(SAIDA, index=False, encoding="utf-8-sig")
    print(f"salvo: {SAIDA.name}")

    print("\n--- categoria (YouTube) ---")
    print(df["categoria"].value_counts().to_string())
    print("\n--- conteudo_final ---")
    print(df["conteudo_final"].value_counts().to_string())


if __name__ == "__main__":
    main()
