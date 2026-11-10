#!/usr/bin/env python3
"""ETAPA 3 - Validar os links do YouTube na YouTube Data API v3.

Entrada : youtube_links.json (lista de objetos com url, subreddits, occurrences...)
Saída   : 03_youtube_validation.jsonl  1 linha por url_id do YouTube, com status, metadados
                                       e os subreddits/ocorrências do link (análise por região)
          03_youtube_cache.jsonl       cada consulta feita à API (permite retomar sem gastar cota)
Todos os arquivos ficam na mesma pasta deste script.

Status possíveis:
  valido           a API devolveu o recurso: o vídeo/canal/playlist existe e é visível hoje
  indisponivel     a API não devolveu nada (removido, privado ou canal encerrado; a API NÃO
                   distingue esses casos) ou o upload consta como rejeitado/falho
  nao_verificavel  formato sem endpoint na API (/c/nome, URL legada, redirect...)
  url_malformada   parece link de vídeo, mas o ID não tem 11 caracteres válidos
  erro_api         a consulta falhou (mensagem no campo 'error')
  pendente         não consultado ainda (ex.: cota acabou no meio) -> rode de novo

Decisões:
- Valida por (tipo, ID), não por url_id: 'youtu.be/X', 'watch?v=X&t=30' e '/shorts/X'
  são consultados uma vez só e o resultado volta para todos os url_id correspondentes.
- Vídeos, canais por ID e playlists vão em lotes de 50 (1 unidade de cota por lote).
  @handle e /user/ precisam de 1 chamada cada.
- Cada resposta é gravada no cache na hora; se a cota acabar, nada se perde.
- 'checked_at' registra quando foi verificado: validade é sempre "na data da consulta".

Uso:
  chave no .env da pasta (YT_API_KEY=... ou YOUTUBE_API_KEY=...)
  python 03_validate_youtube.py --limit 100     # teste pequeno primeiro
  python 03_validate_youtube.py                 # tudo
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from urllib.parse import parse_qs, urlsplit

from pathlib import Path

import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

LINKS = HERE / "youtube_links.json"
CACHE = HERE / "03_youtube_cache.jsonl"
OUT = HERE / "03_youtube_validation.jsonl"
API = "https://www.googleapis.com/youtube/v3"
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
BATCH_KINDS = {  # tipo -> (endpoint, parts)
    "video": ("videos", "snippet,status"),
    "channel_id": ("channels", "snippet"),
    "playlist": ("playlists", "snippet,status"),
}
SINGLE_KINDS = {"handle": "forHandle", "user": "forUsername"}
API_KINDS = set(BATCH_KINDS) | set(SINGLE_KINDS)


# ---------------------------------------------------------------- arquivos
def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl_atomic(path, rows):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------- parser
def parse_youtube(url: str):
    """Retorna (tipo, identificador). tipo: video | video_malformado | channel_id | handle |
    user | custom | playlist | other"""
    url = url.replace("\\", "")              # escape de markdown do Reddit: watch?v=abc\_def
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    parts = [s for s in p.path.split("/") if s]
    q = parse_qs(p.query)

    def vid(x):
        return ("video", x) if VIDEO_ID.match(x) else ("video_malformado", x)

    if host.endswith("youtu.be"):
        return vid(parts[0]) if parts else ("other", None)
    if "v" in q:
        return vid(q["v"][0])
    if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v", "e") and parts[1] != "videoseries":
        return vid(parts[1])
    if parts[:1] == ["attribution_link"] and "u" in q:
        return parse_youtube("https://youtube.com" + q["u"][0])
    if len(parts) >= 2 and parts[0] == "channel":
        return "channel_id", parts[1]
    if parts and parts[0].startswith("@"):
        return "handle", parts[0]
    if len(parts) >= 2 and parts[0] == "user":
        return "user", parts[1]
    if len(parts) >= 2 and parts[0] == "c":
        return "custom", parts[1]
    if "list" in q:
        return "playlist", q["list"][0]
    return "other", None


# ---------------------------------------------------------------- API
class QuotaExceeded(Exception):
    pass


def api_get(endpoint, params, key, tries=4):
    for attempt in range(tries):
        r = requests.get(f"{API}/{endpoint}", params={**params, "key": key}, timeout=30)
        if r.status_code == 200:
            return r.json()
        try:
            reason = r.json()["error"]["errors"][0]["reason"]
        except Exception:
            reason = ""
        if r.status_code == 403 and reason in ("quotaExceeded", "dailyLimitExceeded"):
            raise QuotaExceeded(reason)
        if r.status_code == 429 or r.status_code >= 500:   # erro temporário: espera e tenta de novo
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"{endpoint} HTTP {r.status_code} {reason}: {r.text[:200]}")
    raise RuntimeError(f"{endpoint}: falhou após {tries} tentativas")


def summarize(kind, ident, item):
    rec = {"key": f"{kind}:{ident}", "kind": kind, "ident": ident,
           "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    if item is None:
        return {**rec, "status": "indisponivel"}
    sn, st = item.get("snippet", {}), item.get("status", {})
    is_channel = kind in ("channel_id", "handle", "user")
    rec.update(
        status="valido",
        resolved_id=item["id"],
        title=sn.get("title"),
        channel_id=item["id"] if is_channel else sn.get("channelId"),
        channel_title=sn.get("title") if is_channel else sn.get("channelTitle"),
        published_at=sn.get("publishedAt"),
        privacy=st.get("privacyStatus"),
    )
    if kind == "video":
        rec["category_id"] = sn.get("categoryId")
        rec["upload_status"] = st.get("uploadStatus")
        if st.get("uploadStatus") in ("rejected", "failed", "deleted"):
            rec["status"] = "indisponivel"
    return rec


def check_batch(kind, ids, key):
    endpoint, part = BATCH_KINDS[kind]
    data = api_get(endpoint, {"part": part, "id": ",".join(ids)}, key)
    found = {it["id"]: it for it in data.get("items", [])}
    return [summarize(kind, i, found.get(i)) for i in ids]


def check_single(kind, ident, key):
    data = api_get("channels", {"part": "snippet", SINGLE_KINDS[kind]: ident}, key)
    items = data.get("items", [])
    return summarize(kind, ident, items[0] if items else None)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="valida só os N primeiros links (teste)")
    args = ap.parse_args()

    key = (os.environ.get("YOUTUBE_API_KEY") or os.environ.get("YT_API_KEY")
           or sys.exit("Defina YT_API_KEY (ou YOUTUBE_API_KEY) no .env da pasta"))

    links = json.loads(LINKS.read_text(encoding="utf-8"))
    if args.limit:
        links = links[:args.limit]
    parsed = {l["url_id"]: parse_youtube(l["url"]) for l in links}

    cache = {r["key"]: r for r in read_jsonl(CACHE)} if CACHE.exists() else {}
    pending = {}
    for kind, ident in parsed.values():
        if kind in API_KINDS and f"{kind}:{ident}" not in cache:
            pending.setdefault(kind, set()).add(ident)

    print("=== Etapa 3: validação YouTube ===")
    print(f"links youtube: {len(links)} | já no cache: {len(cache)} | a consultar: "
          + ", ".join(f"{k}={len(v)}" for k, v in pending.items()))

    calls = 0
    try:
        with CACHE.open("a", encoding="utf-8") as cf:
            def save(rec):
                cache[rec["key"]] = rec
                cf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                cf.flush()

            for kind in BATCH_KINDS:
                ids = sorted(pending.get(kind, ()))
                for i in range(0, len(ids), 50):
                    for rec in check_batch(kind, ids[i:i + 50], key):
                        save(rec)
                    calls += 1
                    print(f"  {kind}: {min(i + 50, len(ids))}/{len(ids)}", end="\r")
                if ids:
                    print()
            for kind in SINGLE_KINDS:
                for ident in sorted(pending.get(kind, ())):
                    try:
                        save(check_single(kind, ident, key))
                    except RuntimeError as exc:
                        save({"key": f"{kind}:{ident}", "kind": kind, "ident": ident,
                              "status": "erro_api", "error": str(exc)})
                    calls += 1
    except QuotaExceeded:
        print("\nCota diária esgotada. O progresso está no cache; rode de novo depois.")
    print(f"chamadas à API nesta execução: {calls}")

    # --- monta a saída: 1 linha por url_id ---
    out = []
    for l in links:
        kind, ident = parsed[l["url_id"]]
        if kind in API_KINDS:
            rec = cache.get(f"{kind}:{ident}", {"status": "pendente"})
        elif kind == "video_malformado":
            rec = {"status": "url_malformada"}
        else:
            rec = {"status": "nao_verificavel"}
        out.append({"url_id": l["url_id"], "url": l["url"],
                    "n_occurrences": l["n_occurrences"], "subreddits": l["subreddits"],
                    "kind": kind, "ident": ident,
                    **{k: v for k, v in rec.items() if k not in ("key", "kind", "ident")},
                    "occurrences": l["occurrences"]})

    assert len(out) == len(links), "links perdidos!"
    write_jsonl_atomic(OUT, out)

    # --- relatório ---
    by_status = Counter(o["status"] for o in out)
    by_status_occ = Counter()
    for o in out:
        by_status_occ[o["status"]] += o["n_occurrences"]
    unique = {(o["kind"], o["ident"]): o["status"] for o in out}
    print(f"\n{'status':18s}{'url_ids':>10s}{'ocorrências':>14s}")
    for s, n in by_status.most_common():
        print(f"{s:18s}{n:>10d}{by_status_occ[s]:>14d}")
    print(f"\n(tipo, ID) únicos: {len(unique)}")
    print(f"\n{'tipo':18s}{'status':18s}{'únicos':>8s}")
    for (k, s), n in sorted(Counter((k, s) for (k, _), s in unique.items()).items()):
        print(f"{k:18s}{s:18s}{n:>8d}")


if __name__ == "__main__":
    main()