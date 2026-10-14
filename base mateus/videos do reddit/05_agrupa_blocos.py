#!/usr/bin/env python3
"""ETAPA 5 - Agrupar os vídeos nos três blocos centrais do projeto.

Entrada : youtube_videos_classificados.csv  (saída da etapa 4; usa 'conteudo_final',
                                             que já inclui a revisão manual, se houver)
Saída   : youtube_videos_blocos.csv          todos os vídeos, com a coluna 'bloco'
          blocos_resumo.csv                  1 linha por bloco: nº de vídeos, ocorrências,
                                             subreddits e canais distintos, top 5 de cada
          blocos_por_subreddit.csv           bloco x subreddit (vídeos e ocorrências) -> base
                                             para a análise por região/comunidade

Blocos (mesmos nomes do scripts/classifica_blocos.py do projeto principal):
  autocuidado/estetica  <- autocuidado/estetica, fitness/corpo, saude/sexualidade
  looksmaxxing          <- looksmaxxing
  manosphere/ideologia  <- manosphere/ideologia, relacionamentos/seducao, desenvolvimento_pessoal
  fora do recorte       <- todos os outros temas (música, games, política, ...)
Para mudar algum tema de bloco, edite BLOCOS e rode de novo.

Uso:
  python3 05_agrupa_blocos.py
"""
from collections import Counter
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ENTRADA = HERE / "youtube_videos_classificados.csv"
SAIDA = HERE / "youtube_videos_blocos.csv"
RESUMO = HERE / "blocos_resumo.csv"
POR_SUBREDDIT = HERE / "blocos_por_subreddit.csv"

# tema (conteudo_final) -> bloco; tema que não está aqui vai para FORA
BLOCOS = {
    "autocuidado/estetica": "autocuidado/estetica",
    "fitness/corpo": "autocuidado/estetica",
    "saude/sexualidade": "autocuidado/estetica",
    "looksmaxxing": "looksmaxxing",
    "manosphere/ideologia": "manosphere/ideologia",
    "relacionamentos/seducao": "manosphere/ideologia",
    "desenvolvimento_pessoal": "manosphere/ideologia",
}
FORA = "fora do recorte"


def top(series, n=5):
    return "; ".join(f"{k} ({v})" for k, v in Counter(series).most_common(n))


def main():
    if not ENTRADA.exists():
        raise SystemExit(f"Não encontrei {ENTRADA.name}. Rode o 04_classifica_videos.py antes.")
    df = pd.read_csv(ENTRADA, encoding="utf-8-sig")
    col = "conteudo_final" if "conteudo_final" in df else "conteudo"

    df["bloco"] = df[col].map(BLOCOS).fillna(FORA)
    blocos = df
    print(f"=== Etapa 5: {(df['bloco'] != FORA).sum()} de {len(df)} vídeos nos três blocos "
          f"(coluna usada: {col}) ===")

    cols_ini = ["bloco", "video_id", "url", "title", "channel_title", "categoria"]
    blocos = blocos[cols_ini + [c for c in blocos.columns if c not in cols_ini]]
    blocos = blocos.sort_values(["bloco", col, "n_occurrences"], ascending=[True, True, False])
    blocos.to_csv(SAIDA, index=False, encoding="utf-8-sig")

    # 1 linha por (vídeo, subreddit) para contar por comunidade
    exp = blocos.assign(subreddit=blocos["subreddits"].str.split(";")).explode("subreddit")

    resumo = []
    for b, g in blocos.groupby("bloco"):
        e = exp[exp["bloco"] == b]
        resumo.append({
            "bloco": b,
            "temas": top(g[col], 10),
            "videos": len(g),
            "ocorrencias": int(g["n_occurrences"].sum()),
            "subreddits_distintos": e["subreddit"].nunique(),
            "canais_distintos": g["channel_id"].nunique(),
            "top_subreddits": top(e["subreddit"]),
            "top_canais": top(g["channel_title"]),
            "top_categorias_yt": top(g["categoria"], 3),
        })
    resumo = pd.DataFrame(resumo)
    resumo["_fora"] = resumo["bloco"] == FORA          # "fora do recorte" sempre por último
    resumo = resumo.sort_values(["_fora", "videos"], ascending=[True, False]).drop(columns="_fora")
    resumo.to_csv(RESUMO, index=False, encoding="utf-8-sig")

    por_sub = (exp.groupby(["bloco", "subreddit"])
               .agg(videos=("video_id", "nunique"), ocorrencias=("n_occurrences", "sum"))
               .reset_index().sort_values(["bloco", "videos"], ascending=[True, False]))
    por_sub.to_csv(POR_SUBREDDIT, index=False, encoding="utf-8-sig")

    for r in resumo.itertuples():
        print(f"\n## {r.bloco}: {r.videos} vídeos, {r.ocorrencias} ocorrências, "
              f"{r.subreddits_distintos} subreddits, {r.canais_distintos} canais")
        print(f"   temas:      {r.temas}")
        print(f"   subreddits: {r.top_subreddits}")
        print(f"   canais:     {r.top_canais}")
        print(f"   categorias: {r.top_categorias_yt}")
    print(f"\nsalvo: {SAIDA.name}, {RESUMO.name}, {POR_SUBREDDIT.name}")


if __name__ == "__main__":
    main()
