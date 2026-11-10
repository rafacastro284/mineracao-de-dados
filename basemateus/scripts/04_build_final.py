#!/usr/bin/env python3
"""ETAPA 4 - Juntar tudo numa tabela final.

Entrada : 02_occurrences.jsonl + 02_links.jsonl + 03_validation.jsonl
Saída   : 04_final.jsonl  (1 linha por ocorrência: subreddit + post + link + plataforma + status)

Pode ser re-executado quantas vezes quiser: é só um JOIN, não altera nenhuma tabela anterior.
Links nunca validados saem com status 'not_checked'.
"""
from collections import Counter

from common import FINAL, LINKS, OCC, VALIDATION, ensure_out, read_jsonl, write_jsonl_atomic


def main():
    ensure_out()
    links = {l["url_id"]: l for l in read_jsonl(LINKS)}
    latest = {}
    if VALIDATION.exists():
        for rec in read_jsonl(VALIDATION, tolerant=True):
            latest[rec["url_id"]] = rec

    rows = []
    for occ in read_jsonl(OCC):
        link, val = links[occ["url_id"]], latest.get(occ["url_id"], {})
        rows.append({
            **occ,
            "normalized_url": link["normalized_url"],
            "domain": link["domain"],
            "platform": link["platform"],
            "status": val.get("status", "not_checked"),
            "reason": val.get("reason"),
            "http_status": val.get("http_status"),
            "final_url": val.get("final_url"),
            "checked_at": val.get("checked_at"),
        })

    n_occ = sum(1 for _ in read_jsonl(OCC))
    assert len(rows) == n_occ, "o join mudou o número de ocorrências!"
    write_jsonl_atomic(FINAL, rows)

    print(f"{len(rows)} linhas gravadas em {FINAL}\n")
    table = Counter((r["platform"], r["status"]) for r in rows)
    statuses = ["alive", "dead", "unverified", "not_checked"]
    print(f"{'plataforma':14s}" + "".join(f"{s:>13s}" for s in statuses))
    for p in sorted({k[0] for k in table}):
        print(f"{p:14s}" + "".join(f"{table[(p, s)]:>13d}" for s in statuses))


if __name__ == "__main__":
    main()
