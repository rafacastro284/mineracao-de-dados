#!/usr/bin/env python3
"""ETAPA 9 - Normalizar as transcrições para análise.

Entrada : 06_transcricoes*.jsonl         (saída da etapa 6; lê o principal e as partes)
          youtube_videos_blocos.csv      (bloco, título, canal e subreddits de cada vídeo)
Saída   : 09_transcricoes_normalizadas.csv   1 linha por vídeo com status ok

Segue o mesmo caminho do scripts/lematiza.py da primeira parte do trabalho, adaptado para
fala transcrita (o Whisper já entregou tudo em inglês, então só há um modelo do spaCy):
  - texto_limpo: NFC, sem caracteres invisíveis, espaços padronizados e sem as frases
    repetidas em sequência que o Whisper gera em músicas e silêncios ("Thank you. Thank you...").
    Mantém pontuação, maiúsculas e stopwords: é o texto para embeddings (BERTopic),
    toxicidade e resumos por LLM, que precisam da frase natural.
  - lemas: minúsculas, só palavras, sem stopwords e lematizado. É o texto para
    frequência de palavras, nuvem de palavras e o vetorizador do BERTopic.
  - Menções a dinheiro são extraídas antes de tirar os números ('valores_extraidos'),
    como no lematiza.py, porque monetização é tema central da pesquisa.
  - Stopwords: as do spaCy, menos MANTER_NO_TEXTO (mesma lista do lematiza.py: 2ª pessoa e
    modais carregam a retórica de venda), mais VICIOS_DE_FALA (muletas da fala que dominariam
    a frequência de palavras sem dizer nada sobre o tema).

Colunas de controle, para filtrar antes de cada análise:
  low_content       texto limpo com menos de 50 caracteres (sem fala, só música)
  traduzido         idioma original não é inglês (texto veio da tradução do Whisper)
  repeticao_alta    mais da metade das frases eram repetidas, ou pelo menos LIMITE_LOOP das
                    palavras estão em sequências repetidas coladas ("I I I", "beep beep beep",
                    "I'm not sure. I'm not sure"): provável alucinação do Whisper. Refrões de
                    música ficam em 0,3-0,5 e não são marcados.
  idioma_suspeito   idioma detectado está em IDIOMAS_SUSPEITOS e não foi forçado na etapa 6.
                    O Whisper decide o idioma pelos primeiros 30 s; com música ou silêncio no
                    começo ele chuta nn, cy, jw, la... e a "tradução" vira letra inventada.
                    Vídeos com conteúdo foram refeitos com --idioma (language_forced=True).

Pode rodar enquanto a transcrição está em andamento (só lê os JSONL); rode de novo no fim.

Requisitos: pip install spacy && python3 -m spacy download en_core_web_sm

Uso:
  python3 09_normaliza_transcricoes.py
"""
import glob
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd
import spacy

HERE = Path(__file__).resolve().parent.parent   # scripts/ -> videosDoReddit/
ENTRADA_DIR, CACHE_DIR, RESULTADOS_DIR = HERE / "entrada", HERE / "cache", HERE / "resultados"
BLOCOS = RESULTADOS_DIR / "youtube_videos_blocos.csv"
SAIDA = RESULTADOS_DIR / "09_transcricoes_normalizadas.csv"
MODELO = "en_core_web_sm"
MIN_CARACTERES = 50

# idiomas que o Whisper costuma "detectar" em música, silêncio ou inglês com sotaque/ruído;
# na revisão manual (nov/2026), nenhum vídeo com esses rótulos era de fato falado nesses idiomas
# (só os bhajans em 'sa'/'jw' têm sânscrito/hindi cantado, e continuam suspeitos)
IDIOMAS_SUSPEITOS = {"nn", "cy", "jw", "sn", "la", "haw", "mi", "br", "sa", "yo", "km", "si"}

LIXO_INVISIVEL = ["​", "﻿", "⁠", "‎", "‏"]

# mesma decisão do scripts/lematiza.py: continuam nos lemas
MANTER_NO_TEXTO = {"you", "your", "yours", "yourself", "can", "should", "need", "will", "want"}

# muletas da fala transcrita; documentar no relatório junto com MANTER_NO_TEXTO
VICIOS_DE_FALA = {
    "yeah", "yes", "okay", "ok", "um", "uh", "uhm", "hmm", "huh", "oh", "wow", "hey",
    "like", "know", "mean", "thing", "stuff", "kind", "sort", "lot", "right",
    "actually", "literally", "basically", "gonna", "wanna", "gotta",
}

# dinheiro em inglês: $100, $10,000, 10k, 5 million, 100 dollars, 50 bucks
VALOR = re.compile(
    r"\$\s?\d(?:[\d,.]*\d)?(?:\s?(?:k|thousand|million|billion)\b)?"
    r"|\b\d(?:[\d,.]*\d)?(?:\s?(?:k|thousand|million|billion))?\s?(?:dollars|bucks|usd)\b",
    re.IGNORECASE,
)
FRASES = re.compile(r"(?<=[.!?])\s+")
PALAVRAS = re.compile(r"[a-z']+")
LIMITE_LOOP = 0.75


def carrega_transcricoes():
    """Último registro de cada vídeo nos JSONL; um 'ok' não é substituído por erro (como na etapa 6)."""
    progresso = {}
    for caminho in sorted(glob.glob(str(CACHE_DIR / "06_transcricoes*.jsonl"))):
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                if linha.strip():
                    reg = json.loads(linha)
                    anterior = progresso.get(reg["video_id"])
                    if anterior is None or anterior["status"] != "ok" or reg["status"] == "ok":
                        progresso[reg["video_id"]] = reg
    return [r for r in progresso.values() if r["status"] == "ok"]


def limpa_texto(texto):
    """Devolve (texto limpo, frases repetidas removidas, total de frases)."""
    t = unicodedata.normalize("NFC", str(texto or ""))
    for ch in LIXO_INVISIVEL:
        t = t.replace(ch, "")
    t = re.sub(r"\s+", " ", t.replace(" ", " ")).strip()

    frases = [f for f in FRASES.split(t) if f]
    mantidas = [f for i, f in enumerate(frases) if i == 0 or f.lower() != frases[i - 1].lower()]
    return " ".join(mantidas), len(frases) - len(mantidas), len(frases)


def fracao_em_loop(texto, max_n=4):
    """Fração das palavras que fazem parte de um n-grama (n <= max_n) repetido logo em seguida."""
    palavras = PALAVRAS.findall(texto.lower())
    marcadas = [False] * len(palavras)
    for n in range(1, max_n + 1):
        for i in range(n, len(palavras) - n + 1):
            if palavras[i:i + n] == palavras[i - n:i]:
                marcadas[i - n:i + n] = [True] * (2 * n)
    return sum(marcadas) / len(palavras) if palavras else 0.0


def carrega_modelo():
    try:
        nlp = spacy.load(MODELO, disable=["parser", "ner"])
    except OSError:
        raise SystemExit(f"Modelo '{MODELO}' não instalado. Rode: python3 -m spacy download {MODELO}")
    nlp.max_length = 2_000_000
    for palavra in MANTER_NO_TEXTO:
        nlp.vocab[palavra].is_stop = False
    for palavra in VICIOS_DE_FALA:
        nlp.vocab[palavra].is_stop = True
    return nlp


def lematiza(textos, nlp):
    out = []
    for doc in nlp.pipe((t.lower() for t in textos), batch_size=50):
        lemas = [tok.lemma_ for tok in doc
                 if tok.is_alpha and not tok.is_stop and tok.lemma_ not in VICIOS_DE_FALA
                 and len(tok.lemma_) > 2]
        out.append(" ".join(lemas))
    return out


def main():
    regs = carrega_transcricoes()
    df = pd.DataFrame(regs).reindex(columns=["video_id", "language", "language_forced", "duration_s", "text"])
    df["language_forced"] = df["language_forced"].fillna(False).astype(bool)
    df = df.rename(columns={"language": "idioma_original"})

    limpos = df["text"].map(limpa_texto)
    df["texto_limpo"] = limpos.str[0]
    df["frases_repetidas_removidas"] = limpos.str[1]
    df["repeticao_alta"] = (((limpos.str[2] > 5) & (limpos.str[1] > limpos.str[2] / 2))
                            | (df["texto_limpo"].map(fracao_em_loop) >= LIMITE_LOOP))
    df["low_content"] = df["texto_limpo"].str.len() < MIN_CARACTERES
    df["traduzido"] = df["idioma_original"] != "en"
    df["idioma_suspeito"] = df["idioma_original"].isin(IDIOMAS_SUSPEITOS) & ~df["language_forced"]
    df["n_palavras"] = df["texto_limpo"].str.split().str.len()

    df["valores_extraidos"] = df["texto_limpo"].map(lambda t: VALOR.findall(t))
    df["menciona_valor"] = df["valores_extraidos"].str.len() > 0

    print(f"Lematizando {len(df)} transcrições com {MODELO} ...")
    df["lemas"] = lematiza(df["texto_limpo"].tolist(), carrega_modelo())
    df["n_lemas"] = df["lemas"].str.split().str.len()

    blocos = pd.read_csv(BLOCOS, encoding="utf-8-sig",
                         usecols=["video_id", "bloco", "title", "channel_title", "subreddits"])
    df = blocos.drop_duplicates("video_id").merge(df.drop(columns=["text", "language_forced"]),
                                                   on="video_id", how="right")

    colunas = ["video_id", "bloco", "title", "channel_title", "subreddits", "idioma_original",
               "traduzido", "duration_s", "n_palavras", "n_lemas", "low_content", "repeticao_alta",
               "idioma_suspeito", "frases_repetidas_removidas", "menciona_valor", "valores_extraidos", "texto_limpo", "lemas"]
    df[colunas].to_csv(SAIDA, index=False, encoding="utf-8")

    print(f"\nPronto! {len(df)} transcrições -> {SAIDA.name}")
    print(f"low_content: {int(df['low_content'].sum())} | traduzido: {int(df['traduzido'].sum())} "
          f"| repeticao_alta: {int(df['repeticao_alta'].sum())} "
          f"| idioma_suspeito: {int(df['idioma_suspeito'].sum())} | menciona_valor: {int(df['menciona_valor'].sum())}")
    base = df[~df["low_content"] & ~df["repeticao_alta"] & ~df["idioma_suspeito"]]
    print(f"Base recomendada para análise (sem low_content, repeticao_alta e idioma_suspeito): {len(base)} "
          f"({int((~base['traduzido']).sum())} em inglês original)")
    print("\nPor bloco:\n" + df["bloco"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
