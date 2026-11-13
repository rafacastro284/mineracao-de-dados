#!/usr/bin/env python3
"""ETAPA 3 - Validar quais links ainda estão no ar.

ATENÇÃO: por padrão esta versão valida APENAS os links do YouTube (--platform youtube).
Links de outras plataformas ficam como 'not_checked' na etapa 4. Para validar tudo, use
--platform all; para outra plataforma específica, --platform x (por exemplo).

Entrada : 02_links.jsonl  (só links ÚNICOS)
Saída   : 03_validation.jsonl  (APPEND-ONLY: cada checagem vira uma linha nova, com data)

Três status (de propósito, em vez de só válido/inválido):
  alive       respondeu 2xx/3xx
  dead        404/410, domínio inexistente (DNS), loop de redirect, vídeo do YouTube inexistente
  unverified  não dá para afirmar: 403/429/5xx, timeout, erro de SSL, bloqueio de bot.
              (X, Instagram, Facebook, TikTok bloqueiam robôs: muitos cairão aqui. Isso é
               honesto - "não sei" não é "morto".)

Outras decisões:
- HEAD primeiro (barato); se o servidor reclamar, tenta GET sem baixar o corpo.
- YouTube usa o endpoint oEmbed (a página HTML sempre devolve 200, mesmo p/ vídeo apagado).
- Limite de requisições POR DOMÍNIO (--interval) para não ser bloqueado nem sobrecarregar ninguém.
- Retry só para falhas que podem ser temporárias (timeout, 429, 5xx).
- Retomável: se interromper (Ctrl+C), rode de novo e ele continua de onde parou.
- Antes de começar, testa se há internet - sem isso, tudo viraria 'unverified'.

Uso:
  python 03_validate.py                       # YouTube, só links ainda não checados
  python 03_validate.py --platform all        # todas as plataformas
  python 03_validate.py --platform x          # outra plataforma específica
  python 03_validate.py --retry-unverified    # reprocessa os 'unverified'
  python 03_validate.py --recheck-all         # revalida tudo (gera novo histórico)
  python 03_validate.py --limit 50            # teste pequeno
"""
import argparse
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import requests

from common import LINKS, VALIDATION, ensure_out, read_jsonl

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
TIMEOUT = (5, 15)  # (conectar, ler) em segundos
RETRIES = 2
HEAD_FALLBACK = {400, 403, 404, 405, 406, 429, 500, 501, 503}
DNS_MARKERS = ("Name or service not known", "nodename nor servname", "getaddrinfo failed")

_local = threading.local()


def session():
    """Uma Session por thread (Session não é garantidamente thread-safe)."""
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept": "*/*"})
        _local.s = s
    return s


class DomainThrottle:
    """Garante um intervalo mínimo entre requisições ao mesmo domínio."""
    def __init__(self, interval):
        self.interval, self.lock, self.next_ok = interval, threading.Lock(), {}

    def wait(self, key):
        with self.lock:
            now = time.monotonic()
            slot = max(self.next_ok.get(key, 0), now)
            self.next_ok[key] = slot + self.interval
        if slot > now:
            time.sleep(slot - now)


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def from_exception(exc):
    if isinstance(exc, requests.exceptions.SSLError):
        return "unverified", "ssl_error"
    if isinstance(exc, (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout)):
        return "unverified", "timeout"
    if isinstance(exc, requests.exceptions.TooManyRedirects):
        return "dead", "redirect_loop"
    if isinstance(exc, requests.exceptions.ConnectionError):
        if any(m in str(exc) for m in DNS_MARKERS):
            return "dead", "dns_error"
        return "unverified", "connection_error"
    return "unverified", type(exc).__name__


def classify_http(code):
    if 200 <= code < 400:
        return "alive", "ok"
    if code in (404, 410):
        return "dead", f"http_{code}"
    return "unverified", f"http_{code}"


def fetch(method, url):
    r = session().request(method, url, timeout=TIMEOUT, allow_redirects=True, stream=True)
    try:
        return r.status_code, r.url
    finally:
        r.close()  # stream=True + close: não baixa o corpo da página


def check_http(url):
    """Retorna (status, reason, http_status, final_url, method)."""
    method = "HEAD"
    try:
        code, final = fetch("HEAD", url)
        if code in HEAD_FALLBACK:
            method = "GET"
            code, final = fetch("GET", url)
    except requests.RequestException as exc:
        status, reason = from_exception(exc)
        if status == "dead":
            return status, reason, None, None, "HEAD"
        method = "GET"
        try:
            code, final = fetch("GET", url)
        except requests.RequestException as exc2:
            status, reason = from_exception(exc2)
            return status, reason, None, None, "GET"
    status, reason = classify_http(code)
    return status, reason, code, final, method


def check_youtube(url):
    api = "https://www.youtube.com/oembed?format=json&url=" + quote(url, safe="")
    try:
        code = session().get(api, timeout=TIMEOUT).status_code
    except requests.RequestException as exc:
        status, reason = from_exception(exc)
        return status, reason, None, None, "oembed"
    if code == 200:
        return "alive", "ok", code, None, "oembed"
    if code == 404:
        return "dead", "video_not_found", code, None, "oembed"
    if code in (401, 403):
        return "unverified", "private_or_restricted", code, None, "oembed"
    return "unverified", f"http_{code}", code, None, "oembed"


def uses_oembed(link):
    if link["platform"] != "youtube":
        return False
    p = urlsplit(link["normalized_url"])
    return p.hostname == "youtu.be" or p.path.startswith(("/watch", "/shorts/", "/live/", "/playlist"))


def retryable(reason):
    return reason in ("timeout", "connection_error", "http_429") or reason.startswith("http_5")


def check_link(link, throttle):
    try:
        oembed = uses_oembed(link)
        key = "youtube.com" if oembed else link["domain"]
        for attempt in range(1, RETRIES + 2):
            throttle.wait(key)
            status, reason, code, final, method = (check_youtube if oembed else check_http)(link["normalized_url"])
            if status != "unverified" or not retryable(reason) or attempt > RETRIES:
                break
            time.sleep(2 ** attempt)
    except Exception as exc:  # um bug num link não pode derrubar o lote inteiro
        status, reason, code, final, method, attempt = "unverified", f"internal_error:{type(exc).__name__}", None, None, None, 1
    return {"url_id": link["url_id"], "normalized_url": link["normalized_url"], "checked_at": utcnow(),
            "status": status, "reason": reason, "http_status": code,
            "final_url": final if final != link["normalized_url"] else None,
            "method": method, "attempts": attempt}


def has_internet():
    try:
        requests.head("https://www.wikipedia.org", timeout=5)
        return True
    except requests.RequestException:
        return False


def latest_by_url():
    latest = {}
    if VALIDATION.exists():
        for rec in read_jsonl(VALIDATION, tolerant=True):
            latest[rec["url_id"]] = rec   # arquivo é cronológico: a última linha vence
    return latest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--interval", type=float, default=1.0, help="segundos mínimos entre requisições ao mesmo domínio")
    ap.add_argument("--platform", default="youtube",
                    help="plataforma a validar (padrão: youtube; use 'all' para todas)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--retry-unverified", action="store_true")
    ap.add_argument("--recheck-all", action="store_true")
    ap.add_argument("--skip-preflight", action="store_true")
    args = ap.parse_args()

    ensure_out()
    if not args.skip_preflight and not has_internet():
        sys.exit("Sem acesso à internet: abortando para não gravar resultados enganosos.")

    latest = latest_by_url()
    todo = []
    for link in read_jsonl(LINKS):
        if args.platform != "all" and link["platform"] != args.platform:
            continue
        prev = latest.get(link["url_id"])
        if (args.recheck_all or prev is None
                or (args.retry_unverified and prev["status"] == "unverified")):
            todo.append(link)
    random.Random(42).shuffle(todo)   # intercala domínios: threads não ficam todas esperando o mesmo host
    if args.limit:
        todo = todo[:args.limit]
    print(f"plataforma: {args.platform} | {len(todo)} links para checar ({len(latest)} já tinham histórico)")

    throttle = DomainThrottle(args.interval)
    ex = ThreadPoolExecutor(max_workers=args.workers)
    futures = [ex.submit(check_link, l, throttle) for l in todo]
    done = 0
    try:
        with VALIDATION.open("a", encoding="utf-8") as out:   # só 1 escritor (esta thread)
            for fut in as_completed(futures):
                out.write(json.dumps(fut.result(), ensure_ascii=False) + "\n")
                out.flush()
                done += 1
                if done % 100 == 0:
                    print(f"  {done}/{len(todo)}")
    except KeyboardInterrupt:
        ex.shutdown(wait=False, cancel_futures=True)
        print(f"\nInterrompido após {done} links. Rode de novo para continuar.")
        sys.exit(130)
    ex.shutdown()
    print("Concluído.")


if __name__ == "__main__":
    main()