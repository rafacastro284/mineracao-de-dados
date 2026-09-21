#!/usr/bin/env python3
"""
Lematizacao (PLN) dos titulos + descricoes -- TP1 Mineracao de Dados

Processa cada video no idioma certo (PT -> pt_core_news_sm, EN -> en_core_web_sm)
e gera a coluna 'lemas': o texto ja limpo, sem stopwords e lematizado, pronto
para nuvem de palavras / topic modeling / agrupamento.

Pre-requisitos (rodar UMA vez):
    pip3 install --break-system-packages spacy
    python3 -m spacy download pt_core_news_sm
    python3 -m spacy download en_core_web_sm

Uso (de qualquer pasta):
    python3 lematiza.py

Le:    <raiz>/dados/processados/videos_classificados.csv
Salva: <raiz>/dados/processados/videos_lematizados.csv
"""

import re
from pathlib import Path
import pandas as pd
import spacy

RAIZ = Path(__file__).resolve().parent.parent   # scripts/ -> raiz do projeto
ENTRADA = RAIZ / "dados" / "processados" / "videos_classificados.csv"
SAIDA = RAIZ / "dados" / "processados" / "videos_lematizados.csv"

MAX_CHARS = 2000        # corta descricoes muito longas (links/boilerplate)
MODELOS = {"pt": "pt_core_news_sm", "en": "en_core_web_sm"}

URL = re.compile(r"http\S+|www\.\S+")
SO_LETRAS = re.compile(r"[^a-zà-ÿ\s]")   # mantem letras (com acento) e espacos
ESPACOS = re.compile(r"\s+")


def limpa(texto):
    """Minusculo, remove URLs, emojis, numeros e pontuacao; deixa so palavras."""
    t = str(texto).lower()
    t = URL.sub(" ", t)
    t = SO_LETRAS.sub(" ", t)   # emojis/numeros/pontuacao caem aqui
    t = ESPACOS.sub(" ", t).strip()
    return t[:MAX_CHARS]


def carrega_modelo(nome):
    try:
        # desliga parser e ner: so precisamos de tags/lemas -> bem mais rapido
        return spacy.load(nome, disable=["parser", "ner"])
    except OSError:
        raise SystemExit(
            f"Modelo '{nome}' nao instalado. Rode: python3 -m spacy download {nome}"
        )


def lematiza(textos, nlp):
    """Recebe uma lista de textos limpos e devolve a lista de lemas (string)."""
    out = []
    for doc in nlp.pipe(textos, batch_size=200):
        lemas = [
            tok.lemma_ for tok in doc
            if not tok.is_stop and not tok.is_punct and not tok.is_space
            and len(tok.lemma_) > 2
        ]
        out.append(" ".join(lemas))
    return out


def main():
    if not ENTRADA.exists():
        raise SystemExit(f"Nao encontrei {ENTRADA}. Rode a classificacao antes.")

    df = pd.read_csv(ENTRADA)
    df["texto"] = (df["titulo"].fillna("") + " " + df["descricao"].fillna("")).map(limpa)
    df["lemas"] = ""

    for idioma, modelo in MODELOS.items():
        mask = df["idioma_termo"] == idioma
        n = int(mask.sum())
        if n == 0:
            continue
        print(f"Lematizando {n} videos [{idioma}] com {modelo} ...")
        nlp = carrega_modelo(modelo)
        df.loc[mask, "lemas"] = lematiza(df.loc[mask, "texto"].tolist(), nlp)

    df = df.drop(columns=["texto"])
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SAIDA, index=False)

    vazios = int((df["lemas"].str.len() == 0).sum())
    print(f"\nPronto! {len(df)} videos -> {SAIDA.name}")
    print(f"Videos com lemas vazios (texto curto/sem conteudo util): {vazios}")


if __name__ == "__main__":
    main()