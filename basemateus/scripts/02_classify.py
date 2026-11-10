#!/usr/bin/env python3
"""ETAPA 2 - Normalizar, classificar por plataforma e deduplicar.

Entrada : 01_occurrences_raw.jsonl
Saída   : 02_links.jsonl        1 linha por link ÚNICO (url_id, normalized_url, domain, platform, n_occurrences)
          02_occurrences.jsonl  mesmas ocorrências da etapa 1 + url_id (liga ocorrência -> link)
          02_rejected.jsonl     URLs que não puderam ser normalizadas (nada some em silêncio)

Modelo de dados (2 tabelas ligadas por url_id):
    occurrences (post_id, subreddit, ...) --url_id--> links (url única, plataforma, ...)
Assim a validação roda 1x por link único, e ainda sabemos todos os subreddits que o citaram.

Normalização (conservadora, só o que é seguro):
  host em minúsculas, sem 'www.' (e sem 'm.'/'mobile.' em plataformas conhecidas);
  remove fragmento (#...), credenciais embutidas, barra final, e parâmetros de rastreio
  (utm_*, fbclid, gclid...). NÃO troca http por https e NÃO reordena parâmetros.
  A URL original continua guardada em raw_url nas ocorrências.
"""
from collections import Counter
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from common import (LINKS, OCC, RAW_OCC, REJECTED, ensure_out, make_url_id, read_jsonl,
                    write_jsonl_atomic)

PLATFORMS = {
    "youtube": ("youtube.com", "youtu.be", "youtube-nocookie.com"),
    "x": ("x.com", "twitter.com", "t.co"),
    "reddit": ("reddit.com", "redd.it"),
    "facebook": ("facebook.com", "fb.com", "fb.watch", "fb.me"),
    "instagram": ("instagram.com",),
    "tiktok": ("tiktok.com",),
    "bluesky": ("bsky.app",),
    "threads": ("threads.net", "threads.com"),
    "telegram": ("t.me", "telegram.me"),
    "discord": ("discord.gg", "discord.com"),
    "twitch": ("twitch.tv",),
    "linkedin": ("linkedin.com", "lnkd.in"),
    "github": ("github.com",),
    "wikipedia": ("wikipedia.org",),
    "archive": ("archive.org", "archive.ph", "archive.is", "archive.today"),
    "imgur": ("imgur.com",),
    "substack": ("substack.com",),
    "medium": ("medium.com",),
}
TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref_src", "ref_url"}
YOUTUBE_TRACKING = {"si", "feature"}
MOBILE_PREFIXES = ("m.", "mobile.")


def platform_of(host: str) -> str:
    for name, domains in PLATFORMS.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return name
    return "other"


def normalize(raw: str):
    """Retorna (normalized_url, host, platform) ou None se inválida."""
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not host or "." not in host:
        return None

    if host.startswith("www."):
        host = host[4:]
    platform = platform_of(host)
    if platform != "other":
        for pre in MOBILE_PREFIXES:
            if host.startswith(pre):
                host = host[len(pre):]
        platform = platform_of(host)

    netloc = host + (f":{port}" if port and port not in (80, 443) else "")
    path = parts.path.rstrip("/") if parts.path != "/" else ""

    query = parts.query
    pairs = parse_qsl(query, keep_blank_values=True)
    drop = TRACKING_KEYS | (YOUTUBE_TRACKING if platform == "youtube" else set())
    kept = [(k, v) for k, v in pairs if not k.lower().startswith(TRACKING_PREFIXES) and k.lower() not in drop]
    if len(kept) != len(pairs):          # só reescreve a query se algo foi removido
        query = urlencode(kept)

    normalized = urlunsplit((parts.scheme.lower(), netloc, path, query, ""))
    return normalized, host, platform


def main():
    ensure_out()
    links, occurrences, rejected = {}, [], []
    total = 0

    for occ in read_jsonl(RAW_OCC):
        total += 1
        result = normalize(occ["raw_url"])
        if result is None:
            rejected.append({**occ, "reason": "url_invalida"})
            continue
        normalized, host, platform = result
        uid = make_url_id(normalized)
        if uid not in links:
            links[uid] = {"url_id": uid, "normalized_url": normalized, "domain": host,
                          "platform": platform, "n_occurrences": 0}
        links[uid]["n_occurrences"] += 1
        occurrences.append({**occ, "url_id": uid})

    # --- checagens de integridade: se falhar, nada é gravado ---
    assert total == len(occurrences) + len(rejected), "ocorrências perdidas!"
    assert all(o["url_id"] in links for o in occurrences), "ocorrência apontando para link inexistente"
    assert sum(l["n_occurrences"] for l in links.values()) == len(occurrences), "contagem inconsistente"

    write_jsonl_atomic(LINKS, sorted(links.values(), key=lambda l: (l["platform"], l["domain"], l["url_id"])))
    write_jsonl_atomic(OCC, occurrences)
    write_jsonl_atomic(REJECTED, rejected)

    print("=== Etapa 2: classificação ===")
    print(f"ocorrências lidas: {total} | aceitas: {len(occurrences)} | rejeitadas: {len(rejected)}")
    print(f"links únicos: {len(links)}\n")
    per_platform = Counter(l["platform"] for l in links.values())
    occ_platform = Counter(links[o["url_id"]]["platform"] for o in occurrences)
    print(f"{'plataforma':14s}{'únicos':>10s}{'ocorrências':>14s}")
    for p, n in per_platform.most_common():
        print(f"{p:14s}{n:>10d}{occ_platform[p]:>14d}")
    print("\ntop domínios em 'other':")
    for d, n in Counter(l["domain"] for l in links.values() if l["platform"] == "other").most_common(15):
        print(f"  {d:35s}{n}")


if __name__ == "__main__":
    main()
