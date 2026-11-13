#!/usr/bin/env python3
"""ETAPA 1 - Extrair links dos posts.

Entrada : data/0/subreddits/**/*.json   (somente leitura)
Saída   : data/0/links/01_occurrences_raw.jsonl  (1 linha = 1 link encontrado em 1 post)
          data/0/links/01_extract_errors.jsonl   (arquivos/posts problemáticos)

Decisões:
- NÃO deduplica entre posts: cada (post, link) é uma linha. É isso que preserva o
  rastreio "de qual subreddit veio". A deduplicação global acontece na etapa 2,
  em outra tabela.
- Guarda a URL exatamente como foi encontrada (raw_url), só com limpeza de pontuação.
- Varre 'title' e 'selftext' separados. O campo 'text' parece ser title+selftext
  concatenados; varrê-lo duplicaria tudo.
- Também inclui o campo 'url' quando ele NÃO é o permalink do próprio post.
"""
import html
import json
import re
import sys
from collections import Counter
from urllib.parse import urlsplit

from common import EXTRACT_ERRORS, RAW_OCC, SUBREDDITS_DIR, ensure_out, write_jsonl_atomic

URL_RE = re.compile(r"https?://[^\s<>\"'\]]+", re.IGNORECASE)
TRAILING_PUNCT = ".,;:!?*_~'\""
TEXT_FIELDS = ("title", "selftext")


def clean_url(u: str) -> str:
    """Remove pontuação colada no fim ('veja https://a.com/x.') e ')' sobrando de
    markdown '[txt](https://a.com)', mas preserva ')' balanceado (Wikipedia: /Foo_(bar))."""
    while True:
        before = u
        u = u.rstrip(TRAILING_PUNCT)
        if u.endswith(")") and u.count(")") > u.count("("):
            u = u[:-1]
        if u == before:
            return u


def load_posts(path):
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not all(isinstance(p, dict) for p in data):
        raise ValueError("formato inesperado: esperava objeto ou lista de objetos")
    return data


def is_own_permalink(url: str) -> bool:
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    return host.endswith("reddit.com") and "/comments/" in p.path


def main():
    ensure_out()
    stats = Counter({"posts_duplicados_ignorados": 0, "posts_com_url_nao_permalink": 0})  # zeros aparecem no relatório
    seen_posts = set()
    occurrences, errors = [], []

    files = sorted(SUBREDDITS_DIR.rglob("*.json"))
    if not files:
        sys.exit(f"Nenhum .json em {SUBREDDITS_DIR}")
    for path in files:
        stats["arquivos"] += 1
        rel = path.relative_to(SUBREDDITS_DIR).as_posix()
        try:
            posts = load_posts(path)
        except Exception as exc:  # JSON inválido, encoding, etc.
            errors.append({"file": rel, "error": f"{type(exc).__name__}: {exc}"})
            continue

        for post in posts:
            stats["posts"] += 1
            post_id, sub = post.get("id"), post.get("subreddit")
            if not post_id or not sub:
                errors.append({"file": rel, "error": "post sem id ou subreddit"})
                continue
            if post_id in seen_posts:           # mesmo post em 2 arquivos: não conta 2x
                stats["posts_duplicados_ignorados"] += 1
                continue
            seen_posts.add(post_id)

            candidates = []                      # (campo, texto)
            for field in TEXT_FIELDS:
                candidates.append((field, post.get(field) or ""))
            url_field = post.get("url") or ""
            if url_field and not is_own_permalink(url_field):
                candidates.append(("url", url_field))
                stats["posts_com_url_nao_permalink"] += 1

            found_in_post = set()                # 1 ocorrência por (post, url)
            for field, text in candidates:
                text = html.unescape(text)       # reddit guarda '&amp;' no lugar de '&'
                for match in URL_RE.findall(text):
                    raw = clean_url(match)
                    if len(raw) < 11 or raw in found_in_post:
                        continue
                    found_in_post.add(raw)
                    occurrences.append({
                        "post_id": post_id,
                        "subreddit": sub,
                        "post_timestamp": post.get("timestamp"),
                        "source_file": rel,
                        "field": field,
                        "raw_url": raw,
                    })
            if found_in_post:
                stats["posts_com_links"] += 1

    n = write_jsonl_atomic(RAW_OCC, occurrences)
    write_jsonl_atomic(EXTRACT_ERRORS, errors)

    print("=== Etapa 1: extração ===")
    for k, v in stats.items():
        print(f"{k:32s}{v}")
    print(f"{'ocorrências de links':32s}{n}")
    print(f"{'erros (ver 01_extract_errors)':32s}{len(errors)}")


if __name__ == "__main__":
    main()
