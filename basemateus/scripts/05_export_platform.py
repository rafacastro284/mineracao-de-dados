#!/usr/bin/env python3
"""ETAPA 5 (extra) - Exportar os links de UMA plataforma para um arquivo .json.

Entrada : 04_final.jsonl   (rode a etapa 4 antes, para ela refletir a última validação)
Saída   : <pasta 0>/links/youtube_links.json   (o nome inclui os filtros usados; muda com --out)

Formato padrão (agrupado): 1 item por LINK ÚNICO, com a lista de onde ele apareceu.
    {"url_id": "...", "url": "https://youtu.be/abc", "status": "alive", ...,
     "subreddits": ["50501", "politics"], "n_occurrences": 2,
     "occurrences": [{"subreddit": "50501", "post_id": "...", ...}, ...]}
Assim nada é repetido e o rastreio do subreddit continua completo.

Com --flat: 1 item por OCORRÊNCIA (mesma linha do 04_final), útil para contar por subreddit.

Exemplos:
  python ..\\scripts\\05_export_platform.py                       # todos os links do YouTube
  python ..\\scripts\\05_export_platform.py --status alive        # só os que responderam
  python ..\\scripts\\05_export_platform.py --flat                # 1 linha por ocorrência
  python ..\\scripts\\05_export_platform.py --platform x --out x.json
"""
import argparse
import re
import sys
from urllib.parse import parse_qs, urlsplit

from common import FINAL, LINKS, OUT_DIR, ensure_out, read_jsonl, write_json_atomic

LINK_KEYS = ("status", "reason", "http_status", "final_url", "checked_at")
YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def youtube_video_id(url):
    """ID do vídeo (11 caracteres) ou None (canal, playlist, etc.).
    Serve para reconhecer que youtu.be/X e youtube.com/watch?v=X são o MESMO vídeo."""
    p = urlsplit(url)
    host, parts = (p.hostname or ""), [x for x in p.path.split("/") if x]
    cand = None
    if host == "youtu.be" and parts:
        cand = parts[0]
    elif parts and parts[0] == "watch":
        cand = (parse_qs(p.query).get("v") or [None])[0]
    elif len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v"):
        cand = parts[1]
    return cand if cand and YT_ID.match(cand) else None


OCC_KEYS = ("subreddit", "post_id", "post_timestamp", "field", "raw_url", "source_file")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", default="youtube")
    ap.add_argument("--status", choices=["alive", "dead", "unverified", "not_checked"],
                    help="exporta só links com esse status (padrão: todos)")
    ap.add_argument("--flat", action="store_true", help="1 item por ocorrência em vez de 1 por link")
    ap.add_argument("--out", help="nome do arquivo de saída (dentro de data/0/links)")
    args = ap.parse_args()

    ensure_out()
    if not FINAL.exists():
        sys.exit("04_final.jsonl não existe. Rode antes: python ..\\scripts\\04_build_final.py")

    rows = [r for r in read_jsonl(FINAL)
            if r["platform"] == args.platform and (not args.status or r["status"] == args.status)]

    if args.flat:
        data = rows
    else:
        groups = {}
        for r in rows:
            g = groups.get(r["url_id"])
            if g is None:
                g = groups[r["url_id"]] = {
                    "url_id": r["url_id"], "url": r["normalized_url"], "domain": r["domain"],
                    **{k: r.get(k) for k in LINK_KEYS}, "occurrences": [],
                }
            g["occurrences"].append({k: r.get(k) for k in OCC_KEYS})
        for g in groups.values():
            g["n_occurrences"] = len(g["occurrences"])
            g["subreddits"] = sorted({o["subreddit"] for o in g["occurrences"]})
            if args.platform == "youtube":
                g["video_id"] = youtube_video_id(g["url"])
        data = list(groups.values())

        # --- checagens de integridade ---
        assert sum(g["n_occurrences"] for g in data) == len(rows), "ocorrências perdidas no agrupamento"
        if not args.status:
            esperado = sum(1 for l in read_jsonl(LINKS) if l["platform"] == args.platform)
            assert len(data) == esperado, f"links únicos: {len(data)} no export vs {esperado} em 02_links"

    if not rows:
        sys.exit("Nenhum item encontrado com esses filtros: nada foi gravado.")

    # o nome padrão carrega os filtros, assim uma exportação nunca sobrescreve outra
    suffix = ("_" + args.status if args.status else "") + ("_flat" if args.flat else "")
    out = OUT_DIR / (args.out or f"{args.platform}_links{suffix}.json")
    write_json_atomic(out, data)

    print(f"{len(data)} itens gravados em {out}")
    print(f"({len(rows)} ocorrências; plataforma={args.platform}; status={args.status or 'todos'}; "
          f"formato={'flat' if args.flat else 'agrupado por link'})")


if __name__ == "__main__":
    main()
