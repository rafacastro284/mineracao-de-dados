"""Caminhos e utilidades compartilhadas pelos scripts.

Regra de ouro: NENHUM script escreve em data/0/subreddits (dados brutos = somente leitura).
Tudo que é gerado vai para <pasta 0>/links/.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

def _find_base() -> Path:
    """Localiza a pasta '0' (a que contém 'subreddits'), SEM depender de onde o terminal está.
    Ordem: variável de ambiente REDDIT_BASE; depois pastas vizinhas ao script e ao terminal.
    Se não achar, PARA com erro (rodar 'em silêncio' sobre uma pasta vazia geraria resultados falsos)."""
    env = os.environ.get("REDDIT_BASE")
    here, cwd = Path(__file__).resolve().parent, Path.cwd()
    candidates = [Path(env)] if env else [
        here / "0", here.parent / "0", here / "data" / "0", here.parent / "data" / "0",
        here.parent.parent / "data" / "0", cwd / "0", cwd / "data" / "0",
    ]
    for c in candidates:
        if (c / "subreddits").is_dir():
            print(f"[config] dados em: {c.resolve()}")
            return c.resolve()
    tried = "\n  ".join(str(c) for c in candidates)
    sys.exit(f"Não encontrei a pasta 'subreddits'. Procurei em:\n  {tried}\n"
             "Defina REDDIT_BASE apontando para a pasta que contém 'subreddits'.")


BASE = _find_base()
SUBREDDITS_DIR = BASE / "subreddits"
OUT_DIR = BASE / "links"

RAW_OCC = OUT_DIR / "01_occurrences_raw.jsonl"      # saída da etapa 1
EXTRACT_ERRORS = OUT_DIR / "01_extract_errors.jsonl"
LINKS = OUT_DIR / "02_links.jsonl"                  # links únicos (normalizados)
OCC = OUT_DIR / "02_occurrences.jsonl"              # ocorrências -> url_id
REJECTED = OUT_DIR / "02_rejected.jsonl"            # URLs que não deu para normalizar
VALIDATION = OUT_DIR / "03_validation.jsonl"        # histórico de validações (append-only)
FINAL = OUT_DIR / "04_final.jsonl"                  # tudo junto


def ensure_out():
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def make_url_id(normalized_url: str) -> str:
    """ID determinístico: a mesma URL normalizada sempre gera o mesmo id."""
    return hashlib.sha1(normalized_url.encode("utf-8")).hexdigest()[:16]


def write_jsonl_atomic(path: Path, rows):
    """Escreve num arquivo temporário e só então troca pelo definitivo.
    Se o script cair no meio, o arquivo antigo continua intacto (nunca fica meio-escrito)."""
    tmp = path.with_name(path.name + ".tmp")
    n = 0
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
        f.flush()
        os.fsync(f.fileno())
    _replace_with_retry(tmp, path)
    return n


def _replace_with_retry(tmp: Path, path: Path):
    for attempt in range(10):          # no Windows/OneDrive o arquivo pode estar travado por segundos
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.5)


def write_json_atomic(path: Path, obj):
    """Igual a write_jsonl_atomic, mas para um único documento JSON (lista/objeto)."""
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    _replace_with_retry(tmp, path)


def read_jsonl(path: Path, tolerant: bool = False):
    """Lê JSONL. Com tolerant=True ignora linhas quebradas (ex.: queda de energia
    no meio de um append), avisando na tela."""
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                if not tolerant:
                    raise
                print(f"[aviso] {path.name}: linha {n} corrompida, ignorada")