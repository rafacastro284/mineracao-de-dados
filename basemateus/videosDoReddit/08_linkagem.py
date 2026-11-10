#!/usr/bin/env python3
"""ETAPA 8 - Linkagem: de cada subreddit para os destinos dos seus links.

Liga dois caminhos:
  subreddit -> link direto no post (X, Amazon, Patreon...)
  subreddit -> vídeo do YouTube -> links da descrição do vídeo

Entrada : ../data/0/links/02_links.jsonl e 02_occurrences.jsonl
          youtube_videos_blocos.csv         vídeos válidos, com subreddits e bloco
          04_youtube_detalhes.jsonl         descrição completa dos vídeos
Saída   : 08_dominios_classificados.csv     domínio -> classe e monetização (para revisão manual)
          08_subreddit_dominio.csv          subreddit x domínio (links diretos)
          08_video_destinos.csv             vídeo x link da descrição
          08_caminhos.csv                   subreddit -> vídeo -> domínio de destino
          08_subreddit_resumo.csv           1 linha por subreddit, com proporções (usar para cruzar com toxicidade)
          08_urls_expandidas.jsonl          cache dos encurtadores expandidos

Classificação de monetização (por domínio, não pelo conteúdo da página):
  afiliado               link da Amazon com tag= ou clickbank; indica ganho direto
  afiliado_provavel      amzn.to, geni.us: encurtadores típicos de afiliado, sem tag visível
  loja                   lojas e merchandising; um link da Amazon sem tag pode ser só indicação
  doacao_assinatura      Patreon, Ko-fi, Substack, PayPal...
  curso_produto_digital  Hotmart, Udemy, Gumroad...
  conteudo_adulto_pago   OnlyFans, Fansly
Para mudar a classificação, edite os dicionários abaixo e rode de novo.

Grupos do paper "Mapeando Pontes da Misoginia": pro e anti estão completos. O paper só cita 3 dos 26
subreddits da interseção, então 'intersecao' está incompleto até recebermos a lista inteira.
Limitações: os links vêm das 300 publicações de maior score de cada subreddit da pasta data/0.

Uso:
  python3 08_linkagem.py              # usa os encurtadores que já estão no cache
  python3 08_linkagem.py --expandir   # expande os encurtadores (só segue redirecionamentos)
"""
import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
LINKS = HERE.parent / "data" / "0" / "links" / "02_links.jsonl"
OCORRENCIAS = HERE.parent / "data" / "0" / "links" / "02_occurrences.jsonl"
VIDEOS = HERE / "youtube_videos_blocos.csv"
DETALHES = HERE / "04_youtube_detalhes.jsonl"
CACHE_EXPANSAO = HERE / "08_urls_expandidas.jsonl"

GRUPOS_PAPER = {
    "pro": "askmrp blackpillscience marriedredpill redpillwomen seduction semenretention theredpill",
    "anti": "askfeminists askgaybros askgaybrosover30 asktransgender exredpill incelexit letgirlshavefun "
            "menslib mtf mypartneristrans straighttransgirls",
    "intersecao": "trueunpopularopinion allpilldebate purplepilldebate",
}
GRUPO_DO_SUB = {sub: grupo for grupo, subs in GRUPOS_PAPER.items() for sub in subs.split()}

MONETIZACAO = {
    "afiliado": "clickbank.com clickbank.net",
    "afiliado_provavel": "amzn.to geni.us",
    "loja": "etsy.com shopify.com ebay.com teespring.com spreadshirt.com redbubble.com teepublic.com "
            "merchbar.com bonfire.com spri.ng",
    "doacao_assinatura": "patreon.com ko-fi.com buymeacoffee.com substack.com paypal.com paypal.me cash.app "
                         "venmo.com gofundme.com subscribestar.com memberful.com liberapay.com streamlabs.com",
    "curso_produto_digital": "hotmart.com kiwify.com.br udemy.com teachable.com skool.com kajabi.com "
                             "thinkific.com gumroad.com clickfunnels.com",
    "conteudo_adulto_pago": "onlyfans.com fansly.com",
}
CLASSES = {
    "interno_reddit": "reddit.com redd.it redditmedia.com redditstatic.com",
    "youtube": "youtube.com youtu.be",
    "rede_social": "twitter.com x.com t.co instagram.com facebook.com fb.me tiktok.com twitch.tv discord.gg "
                   "discord.com snapchat.com linkedin.com pinterest.com threads.net telegram.me t.me bsky.app "
                   "vk.com soundcloud.com spotify.com",
    "hospedagem_midia": "imgur.com gfycat.com giphy.com streamable.com tenor.com flickr.com",
    "referencia": "wikipedia.org ncbi.nlm.nih.gov archive.org archive.is archive.ph doi.org",
    "encurtador": "bit.ly goo.gl tinyurl.com ow.ly buff.ly is.gd smarturl.it lnk.to ift.tt linktr.ee",
}
ENCURTADORES = set("bit.ly goo.gl tinyurl.com ow.ly buff.ly is.gd smarturl.it ift.tt amzn.to geni.us t.co fb.me".split())
RE_AMAZON = re.compile(r"(^|\.)amazon\.[a-z.]+$")
RE_TAG = re.compile(r"[?&]tag=", re.IGNORECASE)
RE_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"')\]]+", re.IGNORECASE)


def dominio_de(url):
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "http://" + url
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return host.removeprefix("www.")


def casa(dominio, lista):
    return any(dominio == d or dominio.endswith("." + d) for d in lista.split())


def tipo_monetizacao(dominio, url=""):
    if RE_AMAZON.search(dominio):
        return "afiliado" if RE_TAG.search(url) else "loja"
    for tipo, dominios in MONETIZACAO.items():
        if casa(dominio, dominios):
            return tipo
    return "nenhum"


def classe_de(dominio, tipo):
    if tipo != "nenhum":
        return "monetizacao"
    for classe, dominios in CLASSES.items():
        if casa(dominio, dominios):
            return classe
    return "outro"


def carrega_descricoes():
    descricoes = {}
    with open(DETALHES, encoding="utf-8") as f:
        for linha in f:
            if linha.strip():
                reg = json.loads(linha)
                descricoes[reg["video_id"]] = reg.get("descricao") or ""
    return descricoes


def urls_da_descricao(texto):
    urls = []
    for url in RE_URL.findall(texto):
        url = url.rstrip(".,;:!?*»")
        if "." in dominio_de(url):
            urls.append(url)
    return list(dict.fromkeys(urls))


def carrega_expansoes():
    expandidas = {}
    if CACHE_EXPANSAO.exists():
        with open(CACHE_EXPANSAO, encoding="utf-8") as f:
            for linha in f:
                if linha.strip():
                    reg = json.loads(linha)
                    expandidas[reg["url"]] = reg
    return expandidas


def expande_url(url, sessao):
    """Segue só os redirecionamentos (HEAD, sem baixar o conteúdo). Devolve o último endereço obtido."""
    atual = url if re.match(r"^https?://", url, re.IGNORECASE) else "http://" + url
    erro, status = None, None
    for _ in range(6):
        try:
            r = sessao.head(atual, allow_redirects=False, timeout=10)
        except requests.RequestException as e:
            erro = type(e).__name__
            break
        status = r.status_code
        destino = r.headers.get("Location")
        if not (300 <= r.status_code < 400 and destino):
            break
        atual = urljoin(atual, destino)
    return {"url": url, "url_final": atual, "status": status, "erro": erro,
            "expandido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def expande_encurtadores(urls, expandidas):
    pendentes = [u for u in urls if u not in expandidas and dominio_de(u) in ENCURTADORES]
    print(f"Expandindo {len(pendentes)} encurtadores...")
    sessao = requests.Session()
    sessao.headers["User-Agent"] = "Mozilla/5.0 (pesquisa academica; expansao de links)"
    with open(CACHE_EXPANSAO, "a", encoding="utf-8") as f:
        for i, url in enumerate(pendentes, 1):
            reg = expande_url(url, sessao)
            expandidas[url] = reg
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
            f.flush()
            if i % 100 == 0:
                print(f"  {i}/{len(pendentes)}", flush=True)
            time.sleep(0.5)


def tabela_links_diretos():
    links = {}
    with open(LINKS, encoding="utf-8") as f:
        for linha in f:
            reg = json.loads(linha)
            links[reg["url_id"]] = reg

    linhas = []
    with open(OCORRENCIAS, encoding="utf-8") as f:
        for linha in f:
            occ = json.loads(linha)
            link = links[occ["url_id"]]
            dominio = (link.get("domain") or "").lower().removeprefix("www.")
            tipo = tipo_monetizacao(dominio, occ.get("raw_url") or "")
            linhas.append({
                "subreddit": occ["subreddit"].lower(),
                "post_id": occ["post_id"],
                "url_id": occ["url_id"],
                "dominio": dominio,
                "classe": classe_de(dominio, tipo),
                "tipo_monetizacao": tipo,
            })
    return pd.DataFrame(linhas)


def tabela_destinos(videos, descricoes, expandidas):
    linhas = []
    for video_id in videos["video_id"]:
        for url in urls_da_descricao(descricoes.get(video_id, "")):
            exp = expandidas.get(url)
            url_final = exp["url_final"] if exp and not exp["erro"] else url
            dominio = dominio_de(url_final)
            tipo = tipo_monetizacao(dominio, url_final)
            linhas.append({
                "video_id": video_id,
                "url": url,
                "url_final": url_final,
                "dominio": dominio,
                "classe": classe_de(dominio, tipo),
                "tipo_monetizacao": tipo,
                "expandido": bool(exp and not exp["erro"]),
            })
    return pd.DataFrame(linhas)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--expandir", action="store_true", help="expande os encurtadores das descrições")
    args = ap.parse_args()

    videos = pd.read_csv(VIDEOS, encoding="utf-8-sig", usecols=["video_id", "bloco", "subreddits"])
    videos["video_id"] = videos["video_id"].astype(str)
    descricoes = carrega_descricoes()
    expandidas = carrega_expansoes()
    if args.expandir:
        todas = {u for v in videos["video_id"] for u in urls_da_descricao(descricoes.get(v, ""))}
        expande_encurtadores(sorted(todas), expandidas)

    # Caminho 1: subreddit -> link direto
    diretos = tabela_links_diretos()
    subreddit_dominio = (diretos.groupby(["subreddit", "dominio", "classe", "tipo_monetizacao"])
                         .agg(n_ocorrencias=("url_id", "size"), n_links=("url_id", "nunique"), n_posts=("post_id", "nunique"))
                         .reset_index())
    subreddit_dominio.insert(1, "grupo_paper", subreddit_dominio["subreddit"].map(GRUPO_DO_SUB).fillna("nao_classificado"))
    subreddit_dominio.to_csv(HERE / "08_subreddit_dominio.csv", index=False, encoding="utf-8")

    # Caminho 2: subreddit -> vídeo -> destino da descrição
    destinos = tabela_destinos(videos, descricoes, expandidas)
    destinos.to_csv(HERE / "08_video_destinos.csv", index=False, encoding="utf-8")

    sub_video = videos.assign(subreddit=videos["subreddits"].fillna("").str.lower().str.split(";")).explode("subreddit")
    sub_video["subreddit"] = sub_video["subreddit"].str.strip()
    sub_video = sub_video[sub_video["subreddit"] != ""][["subreddit", "video_id", "bloco"]].drop_duplicates()
    caminhos = sub_video.merge(destinos[["video_id", "dominio", "classe", "tipo_monetizacao"]].drop_duplicates(),
                               on="video_id", how="left")
    caminhos.insert(1, "grupo_paper", caminhos["subreddit"].map(GRUPO_DO_SUB).fillna("nao_classificado"))
    caminhos.to_csv(HERE / "08_caminhos.csv", index=False, encoding="utf-8")

    # Domínios para revisão manual
    dominios = defaultdict(lambda: {"n_ocorrencias_reddit": 0, "n_videos_descricao": 0})
    for dominio, n in diretos["dominio"].value_counts().items():
        dominios[dominio]["n_ocorrencias_reddit"] = int(n)
    for dominio, n in destinos.drop_duplicates(["video_id", "dominio"])["dominio"].value_counts().items():
        dominios[dominio]["n_videos_descricao"] = int(n)
    tabela = pd.DataFrame([{"dominio": d, **c} for d, c in dominios.items()])
    tabela["tipo_monetizacao"] = tabela["dominio"].map(tipo_monetizacao)
    tabela["classe"] = [classe_de(d, t) for d, t in zip(tabela["dominio"], tabela["tipo_monetizacao"])]
    tabela = tabela.sort_values(["n_ocorrencias_reddit", "n_videos_descricao"], ascending=False)
    tabela.to_csv(HERE / "08_dominios_classificados.csv", index=False, encoding="utf-8")

    # Resumo por subreddit: proporções, porque subreddits grandes têm mais links
    externos = diretos[diretos["classe"] != "interno_reddit"]
    resumo = diretos.groupby("subreddit").agg(n_ocorrencias=("url_id", "size"), n_posts_com_link=("post_id", "nunique"))
    resumo["n_externas"] = externos.groupby("subreddit").size()
    resumo["n_youtube"] = diretos[diretos["classe"] == "youtube"].groupby("subreddit").size()
    monetizados = externos[externos["tipo_monetizacao"] != "nenhum"]
    resumo["n_monetizadas"] = monetizados.groupby("subreddit").size()
    por_tipo = monetizados.pivot_table(index="subreddit", columns="tipo_monetizacao", values="url_id",
                                       aggfunc="size", fill_value=0).add_prefix("n_")
    resumo = resumo.join(por_tipo)

    videos_com_monetizacao = set(destinos.loc[destinos["tipo_monetizacao"] != "nenhum", "video_id"])
    resumo["n_videos_validos"] = sub_video.groupby("subreddit")["video_id"].nunique()
    resumo["n_videos_com_monetizacao"] = (sub_video[sub_video["video_id"].isin(videos_com_monetizacao)]
                                          .groupby("subreddit")["video_id"].nunique())
    resumo = resumo.fillna(0).astype(int)
    resumo["prop_monetizada"] = (resumo["n_monetizadas"] / resumo["n_externas"].replace(0, pd.NA)).astype("Float64").round(4)
    resumo["prop_videos_monetizados"] = (resumo["n_videos_com_monetizacao"]
                                         / resumo["n_videos_validos"].replace(0, pd.NA)).astype("Float64").round(4)
    resumo.insert(0, "grupo_paper", resumo.index.map(lambda s: GRUPO_DO_SUB.get(s, "nao_classificado")))
    resumo.sort_values("n_ocorrencias", ascending=False).to_csv(HERE / "08_subreddit_resumo.csv", encoding="utf-8")

    print(f"Links diretos: {len(diretos)} ocorrências em {diretos['subreddit'].nunique()} subreddits; "
          f"{len(externos)} externas; {len(monetizados)} monetizadas")
    print(f"Descrições: {destinos['video_id'].nunique()} vídeos com link; {len(destinos)} links; "
          f"{len(videos_com_monetizacao)} vídeos com monetização; {int(destinos['expandido'].sum())} links expandidos")


if __name__ == "__main__":
    main()
