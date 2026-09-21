#!/usr/bin/env python3
"""
Lematizacao (PLN) dos titulos + descricoes -- TP1 Mineracao de Dados

Processa cada video no idioma certo (PT -> pt_core_news_sm, EN -> en_core_web_sm)
e gera a coluna 'lemas': o texto ja limpo, sem stopwords (customizadas) e
lematizado, pronto para nuvem de palavras / topic modeling / agrupamento.

AJUSTES DESTA VERSAO:
  1) Antes de remover numeros do texto, extrai mencoes monetarias/numericas
     (ex.: "R$50 mil", "10k", "3 meses") para colunas separadas
     ('menciona_valor' e 'valores_extraidos'), porque esse sinal e central
     pro tema da pesquisa (venda de riqueza/status) e nao pode ser perdido
     na limpeza.
  2) Idioma usado para escolher o modelo de lematizacao deixa de ser so
     'idioma_termo' (que reflete o termo de busca, nao o video em si).
     Prioridade: idioma_video (metadado do YouTube) -> langdetect no texto
     -> idioma_termo como ultimo recurso. Fica salvo em 'idioma_real'.
  3) Emojis sao extraidos para a coluna 'emojis' ANTES da limpeza, em vez
     de serem simplesmente descartados (carregam sinal emocional no nicho).
  4) (NOVO) Stopwords customizadas por idioma: pronomes de 2a pessoa
     ("voce", "you") e verbos modais/de comando ("pode", "precisa", "can",
     "should") sao RETIRADOS da lista de stopwords do spaCy -- ou seja,
     continuam aparecendo nos lemas em vez de serem descartados -- porque
     carregam o sinal de retorica persuasiva/venda que e objeto da pesquisa.
     A lista fica em MANTER_NO_TEXTO, documentada logo abaixo, e e aplicada
     dentro de carrega_modelo().

Pre-requisitos (rodar UMA vez):
    pip3 install --break-system-packages spacy langdetect emoji
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
import emoji
from langdetect import detect, DetectorFactory, LangDetectException

# langdetect e probabilistico por padrao; fixar a seed deixa o resultado
# reprodutivel entre execucoes (importante para um trabalho academico).
DetectorFactory.seed = 42

RAIZ = Path(__file__).resolve().parent.parent   # scripts/ -> raiz do projeto
ENTRADA = RAIZ / "dados" / "processados" / "videos_classificados.csv"
SAIDA = RAIZ / "dados" / "processados" / "videos_lematizados.csv"

MAX_CHARS = 2000        # corta descricoes muito longas (links/boilerplate)
MODELOS = {"pt": "pt_core_news_sm", "en": "en_core_web_sm"}

# --- (4) Stopwords customizadas por idioma ---
# Palavras que o spaCy remove por padrao, mas que carregam sinal retorico
# relevante pro tema (persuasao / 2a pessoa / comando) -- por isso sao
# RETIRADAS da lista de stopwords (continuam aparecendo nos lemas, nao
# sao mais descartadas). Decisao documentada tambem no relatorio.
MANTER_NO_TEXTO = {
    "pt": {
        # pronomes de 2a pessoa (nucleo da retorica de venda direta)
        "você", "voce", "tu", "vc", "vcs", "vocês", "voces",
        "te", "ti", "teu", "tua", "teus", "tuas",
        "seu", "sua", "seus", "suas",
        # verbos modais/imperativos de comando ou promessa
        "pode", "podes", "poder", "deve", "deves", "dever",
        "precisa", "precisas", "precisar",
        "vai", "vais",
        "quer", "queres", "querer",
    },
    "en": {
        "you", "your", "yours", "yourself",
        "can", "should", "need", "will", "want",
    },
}

URL = re.compile(r"http\S+|www\.\S+")
SO_LETRAS = re.compile(r"[^a-zà-ÿ\s]")   # mantem letras (com acento) e espacos
ESPACOS = re.compile(r"\s+")

# --- (1) Regex para mencoes monetarias/numericas de status ---
# cobre: R$50, R$ 50 mil, $100, 10k, 3 milhoes, 2 milhões etc.
VALOR = re.compile(
    r"r?\$\s?\d+[\.,]?\d*\s?(?:mil|k|milh(?:a|ã)o|milh(?:o|õ)es)?",
    re.IGNORECASE,
)


def extrai_valores(texto):
    """Devolve a lista de mencoes monetarias/numericas encontradas no texto bruto."""
    return VALOR.findall(str(texto).lower())


def limpa(texto):
    """Minusculo, remove URLs, emojis, numeros e pontuacao; deixa so palavras.

    Chamada DEPOIS de extrair valores e emojis (ver main()), entao remover
    numeros aqui nao perde mais o sinal -- ele ja foi capturado a parte.
    """
    t = str(texto).lower()
    t = URL.sub(" ", t)
    t = SO_LETRAS.sub(" ", t)   # emojis/numeros/pontuacao caem aqui
    t = ESPACOS.sub(" ", t).strip()
    return t[:MAX_CHARS]


def extrai_emojis(texto):
    """(3) Devolve so os emojis presentes no texto, concatenados em string."""
    return "".join(c for c in str(texto) if c in emoji.EMOJI_DATA)


def idioma_real(row):
    """(2) Decide o idioma a usar na lematizacao, com fallback em 3 niveis:
    1. idioma_video (metadado do proprio YouTube, quando preenchido)
    2. deteccao automatica via langdetect no texto bruto
    3. idioma_termo (termo de busca) como ultimo recurso
    """
    iv = row.get("idioma_video")
    if pd.notna(iv) and str(iv).strip():
        # normaliza algo como "pt-BR" / "en-US" para "pt" / "en"
        return str(iv).strip().lower()[:2]

    texto = str(row.get("texto_bruto", "")).strip()
    if len(texto) >= 20:   # texto curto demais deixa o langdetect muito instavel
        try:
            det = detect(texto)[:2]
            if det in MODELOS:
                return det
        except LangDetectException:
            pass

    return str(row.get("idioma_termo", "")).strip().lower()[:2]


def carrega_modelo(nome, idioma):
    """Carrega o modelo spaCy e aplica a lista de stopwords customizada (4)
    correspondente ao idioma -- ou seja, remove essas palavras da lista de
    stopwords do modelo, entao elas passam a APARECER nos lemas.
    """
    try:
        # desliga parser e ner: so precisamos de tags/lemas -> bem mais rapido
        nlp = spacy.load(nome, disable=["parser", "ner"])
    except OSError:
        raise SystemExit(
            f"Modelo '{nome}' nao instalado. Rode: python3 -m spacy download {nome}"
        )

    for palavra in MANTER_NO_TEXTO.get(idioma, set()):
        nlp.vocab[palavra].is_stop = False

    return nlp


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

    # texto bruto (titulo + descricao), ainda sem nenhuma limpeza --
    # e a partir dele que extraimos valores, emojis e detectamos idioma
    df["texto_bruto"] = (df["titulo"].fillna("") + " " + df["descricao"].fillna(""))

    # (1) extrai mencoes monetarias/numericas ANTES de qualquer limpeza
    df["valores_extraidos"] = df["texto_bruto"].map(extrai_valores)
    df["menciona_valor"] = df["valores_extraidos"].map(lambda v: len(v) > 0)

    # (3) extrai emojis ANTES da limpeza
    df["emojis"] = df["texto_bruto"].map(extrai_emojis)

    # (2) decide o idioma real a usar, video a video
    print("Detectando idioma real (idioma_video -> langdetect -> idioma_termo) ...")
    df["idioma_real"] = df.apply(idioma_real, axis=1)

    # agora sim, limpa o texto para a lematizacao (numeros ja foram capturados acima)
    df["texto"] = df["texto_bruto"].map(limpa)
    df["lemas"] = ""

    for idioma, modelo in MODELOS.items():
        mask = df["idioma_real"] == idioma
        n = int(mask.sum())
        if n == 0:
            continue
        print(f"Lematizando {n} videos [{idioma}] com {modelo} "
              f"(stopwords customizadas: {len(MANTER_NO_TEXTO.get(idioma, set()))} palavras mantidas) ...")
        nlp = carrega_modelo(modelo, idioma)
        df.loc[mask, "lemas"] = lematiza(df.loc[mask, "texto"].tolist(), nlp)

    # videos cujo idioma_real nao caiu em 'pt' nem 'en' ficam sem lema --
    # vale saber quantos sao, para decidir se precisam de um terceiro modelo
    sem_modelo = df.loc[~df["idioma_real"].isin(MODELOS), "idioma_real"].value_counts()
    if len(sem_modelo):
        print("\n(idiomas detectados sem modelo de lematizacao disponivel:)")
        print(sem_modelo.to_string())

    df = df.drop(columns=["texto", "texto_bruto"])
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SAIDA, index=False)

    vazios = int((df["lemas"].str.len() == 0).sum())
    com_valor = int(df["menciona_valor"].sum())
    com_emoji = int((df["emojis"].str.len() > 0).sum())
    print(f"\nPronto! {len(df)} videos -> {SAIDA.name}")
    print(f"Videos com lemas vazios (texto curto/sem conteudo util): {vazios}")
    print(f"Videos com mencao a valor monetario/numerico: {com_valor}")
    print(f"Videos com pelo menos 1 emoji: {com_emoji}")
    print("\n== IDIOMA REAL USADO (apos fallback idioma_video -> langdetect -> idioma_termo) ==")
    print(df["idioma_real"].value_counts().to_string())


if __name__ == "__main__":
    main()