#!/usr/bin/env python3
"""
Topic modeling com BERTopic -- TP1 Mineracao de Dados (script UNICO)

Faz tudo em um arquivo so:
  1) Roda BERTopic por idioma (pt/en) sobre a coluna 'lemas'.
  2) Reduz para NR_TOPICOS_REDUZIDOS (igual ao exemplo: muitos topicos brutos
     -> poucos topicos interpretaveis).
  3) Exporta uma planilha 'topicos_<idioma>_PARA_CLASSIFICAR.csv' com as
     palavras-chave e exemplos de titulo de cada topico.
  4) *** ETAPA MANUAL (fora do codigo): *** abra essa planilha no Excel/
     Sheets e preencha a coluna 'categoria_manual' (ex.: "comercial" /
     "nao_comercial"), olhando 'Name' + 'exemplos_titulo'. Salve por cima,
     mesmo nome, mesmo formato CSV.
  5) Rode o script de novo: ele detecta que a planilha ja foi preenchida e
     automaticamente junta a classificacao na base inteira de videos, gerando
     'videos_com_categoria_topico.csv' -- pronto para o relatorio.

Ou seja: RODE ESTE SCRIPT DUAS VEZES.
  - 1a vez: gera as planilhas PARA_CLASSIFICAR (categoria_manual vazia).
  - Voce preenche a mao.
  - 2a vez: gera o resultado final ja com a classificacao aplicada.

Le:    <raiz>/dados/processados/videos_lematizados.csv
Salva: <raiz>/dados/processados/resultados/  (varios arquivos, ver abaixo)

Uso:
    pip3 install --break-system-packages bertopic sentence-transformers pandas umap-learn hdbscan
    python3 topic_modeling_bertopic.py
"""

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer

sns.set_theme(style="whitegrid")

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA = RAIZ / "dados" / "processados" / "videos_lematizados.csv"
SAIDA_DIR = RAIZ / "dados" / "processados" / "resultados"
SAIDA_FINAL = SAIDA_DIR / "videos_com_categoria_topico.csv"

MIN_LEN_LEMAS = 15          # caracteres minimos em 'lemas' para entrar no modelo
MIN_TOPIC_SIZE = 8          # quantos videos, no minimo, para formar um topico
NR_TOPICOS_REDUZIDOS = 15   # ajuste conforme o que sair do seu corpus

MODELO_EMBEDDING = "paraphrase-multilingual-MiniLM-L12-v2"


# ============================================================
# PARTE 1 -- rodar BERTopic e gerar a planilha para classificar
# ============================================================

def roda_bertopic(textos, idioma):
    print(f"\n=== BERTopic [{idioma}] -- {len(textos)} videos ===")
    if len(textos) < MIN_TOPIC_SIZE * 2:
        print(f"AVISO: poucos videos ({len(textos)}) para um topic modeling "
              f"confiavel neste idioma. Trate como exploratorio.")

    embedder = SentenceTransformer(MODELO_EMBEDDING)
    topic_model = BERTopic(
        embedding_model=embedder,
        min_topic_size=MIN_TOPIC_SIZE,
        language="multilingual",
        calculate_probabilities=False,
        verbose=True,
    )
    topicos, _ = topic_model.fit_transform(textos)

    info = topic_model.get_topic_info()
    n_brutos = len(info) - 1
    print(f"\nTopicos brutos (excluindo -1 = outliers): {n_brutos}")
    print(info[["Topic", "Count", "Name"]].to_string(index=False))

    if n_brutos > NR_TOPICOS_REDUZIDOS:
        print(f"\nReduzindo de {n_brutos} para {NR_TOPICOS_REDUZIDOS} topicos ...")
        topic_model.reduce_topics(textos, nr_topics=NR_TOPICOS_REDUZIDOS)
        topicos = topic_model.topics_
        info = topic_model.get_topic_info()
        print(f"Topicos apos reducao: {len(info) - 1}")
        print(info[["Topic", "Count", "Name"]].to_string(index=False))
    else:
        print(f"\n(ja saiu com {n_brutos} topicos, <= {NR_TOPICOS_REDUZIDOS} -- sem reducao)")

    return topic_model, topicos, info


def grafico_topicos_png(info, idioma):
    """Grafico de barras (PNG, estatico) com a contagem de videos por topico
    -- versao para colar direto no relatorio (o HTML interativo continua
    sendo gerado tambem, mas esse aqui abre como imagem normal)."""
    dados = info[info["Topic"] != -1].sort_values("Count", ascending=False)
    plt.figure(figsize=(9, max(4, 0.4 * len(dados))))
    sns.barplot(data=dados, x="Count", y="Name", hue="Name", legend=False, palette="viridis")
    plt.xlabel("Numero de videos")
    plt.ylabel("Topico")
    plt.title(f"Videos por topico -- BERTopic [{idioma}]")
    plt.tight_layout()
    caminho = SAIDA_DIR / f"grafico_topicos_{idioma}.png"
    plt.savefig(caminho, dpi=150)
    plt.close()
    print(f">>> Grafico PNG salvo: {caminho}")


def gera_planilha_classificar(sub, info, idioma):
    """Gera (ou mantem, se ja existir preenchida) a planilha de classificacao
    manual: 1 linha por topico reduzido, com palavras-chave + exemplos."""
    caminho = SAIDA_DIR / f"topicos_{idioma}_PARA_CLASSIFICAR.csv"

    info_manual = info[info["Topic"] != -1][["Topic", "Count", "Name"]].copy()
    exemplos = (
        sub[sub["topico_bertopic"] != -1]
        .groupby("topico_bertopic")["titulo"]
        .apply(lambda s: " | ".join(s.head(3)))
        .rename("exemplos_titulo")
    )
    info_manual = info_manual.merge(exemplos, left_on="Topic", right_index=True, how="left")
    info_manual["categoria_manual"] = ""
    info_manual.to_csv(caminho, index=False)

    print(f"\n>>> Planilha para classificacao manual: {caminho}")
    print(">>> Abra no Excel/Sheets, leia 'Name' + 'exemplos_titulo' de cada "
          "topico e preencha 'categoria_manual' (ex.: comercial / nao_comercial).")
    return caminho


def roda_topic_modeling():
    """Roda o pipeline completo do BERTopic."""
    if not ENTRADA.exists():
        raise SystemExit(f"Nao encontrei {ENTRADA}. Rode o pre-processamento antes.")

    SAIDA_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(ENTRADA)
    df["lemas"] = df["lemas"].fillna("")
    df_valido = df[df["lemas"].str.len() >= MIN_LEN_LEMAS].copy()
    descartados = len(df) - len(df_valido)
    print(f"Videos descartados por lema curto/vazio (< {MIN_LEN_LEMAS} chars): {descartados}")

    for idioma in ["pt", "en"]:
        sub = df_valido[df_valido["idioma_real"] == idioma].copy()
        if len(sub) < MIN_TOPIC_SIZE:
            print(f"\n[{idioma}] Videos insuficientes ({len(sub)}) -- pulando.")
            continue

        topic_model, topicos, info = roda_bertopic(sub["lemas"].tolist(), idioma)
        sub["topico_bertopic"] = topicos

        colunas = [c for c in ["video_id", "titulo", "bloco", "menciona_valor",
                                "views", "topico_bertopic"] if c in sub.columns]
        sub[colunas].to_csv(SAIDA_DIR / f"topicos_{idioma}.csv", index=False)
        info.to_csv(SAIDA_DIR / f"topicos_{idioma}_resumo.csv", index=False)

        gera_planilha_classificar(sub, info, idioma)
        grafico_topicos_png(info, idioma)

        try:
            topic_model.visualize_barchart(top_n_topics=12).write_html(
                SAIDA_DIR / f"topicos_{idioma}_barchart.html")
            topic_model.visualize_topics().write_html(
                SAIDA_DIR / f"topicos_{idioma}_mapa.html")
        except Exception as e:
            print(f"AVISO: nao consegui gerar os graficos interativos ({e}).")


# ============================================================
# PARTE 2 -- juntar a classificacao manual (se ja preenchida)
# ============================================================

def planilha_esta_preenchida(caminho):
    if not caminho.exists():
        return False
    manual = pd.read_csv(caminho)
    if "categoria_manual" not in manual.columns:
        return False
    preenchido = manual["categoria_manual"].fillna("").astype(str).str.strip() != ""
    return preenchido.any()


def graficos_resultado_final(final):
    """Graficos PNG do resultado final: distribuicao de categoria_topico,
    e categoria_topico x bloco (barras empilhadas)."""
    plt.figure(figsize=(7, 5))
    contagem = final["categoria_topico"].value_counts()
    sns.barplot(x=contagem.values, y=contagem.index, hue=contagem.index,
                legend=False, palette="rocket")
    plt.xlabel("Numero de videos")
    plt.ylabel("Categoria (classificacao manual dos topicos)")
    plt.title("Distribuicao final por categoria_topico")
    plt.tight_layout()
    plt.savefig(SAIDA_DIR / "grafico_categoria_topico.png", dpi=150)
    plt.close()

    if "bloco" in final.columns:
        cruz = pd.crosstab(final["bloco"], final["categoria_topico"], normalize="index")
        cruz.plot(kind="barh", stacked=True, figsize=(9, 5), colormap="viridis")
        plt.xlabel("Proporcao dentro do bloco")
        plt.ylabel("Bloco tematico (classificacao manual antiga)")
        plt.title("categoria_topico x bloco (proporcao)")
        plt.legend(title="categoria_topico", bbox_to_anchor=(1.02, 1), loc="upper left")
        plt.tight_layout()
        plt.savefig(SAIDA_DIR / "grafico_categoria_topico_x_bloco.png", dpi=150)
        plt.close()

    print(f">>> Graficos PNG do resultado final salvos em {SAIDA_DIR}")


def junta_classificacao_manual():
    """Le as planilhas PARA_CLASSIFICAR (ja preenchidas) + os CSVs de video
    por topico, e gera a base final com a coluna 'categoria_topico'."""
    partes = []
    for idioma in ["pt", "en"]:
        f_videos = SAIDA_DIR / f"topicos_{idioma}.csv"
        f_manual = SAIDA_DIR / f"topicos_{idioma}_PARA_CLASSIFICAR.csv"
        if not f_videos.exists() or not f_manual.exists():
            continue

        videos = pd.read_csv(f_videos)
        manual = pd.read_csv(f_manual)

        vazios = manual["categoria_manual"].isna() | (manual["categoria_manual"].astype(str).str.strip() == "")
        if vazios.any():
            print(f"\n[AVISO - {idioma}] {vazios.sum()} topico(s) ainda sem classificacao manual:")
            print(manual.loc[vazios, ["Topic", "Name"]].to_string(index=False))

        manual["categoria_manual"] = manual["categoria_manual"].fillna("").astype(str).str.strip()
        manual.loc[manual["categoria_manual"] == "", "categoria_manual"] = "nao_classificado"

        mapa = dict(zip(manual["Topic"], manual["categoria_manual"]))
        videos["categoria_topico"] = videos["topico_bertopic"].map(mapa).fillna("nao_classificado")
        videos["idioma_real"] = idioma
        partes.append(videos)

    if not partes:
        return

    final = pd.concat(partes, ignore_index=True)
    final.to_csv(SAIDA_FINAL, index=False)

    print(f"\n>>> Classificacao manual detectada -- gerando resultado final!")
    print(f"Pronto! {len(final)} videos -> {SAIDA_FINAL.name}")
    print("\n== DISTRIBUICAO FINAL POR categoria_topico ==")
    print(final["categoria_topico"].value_counts())
    if "bloco" in final.columns:
        print("\n== categoria_topico x bloco (classificacao manual antiga) ==")
        print(pd.crosstab(final["categoria_topico"], final["bloco"]))

    graficos_resultado_final(final)


# ============================================================
# MAIN
# ============================================================

def main():
    planilhas = [SAIDA_DIR / f"topicos_{idioma}_PARA_CLASSIFICAR.csv" for idioma in ["pt", "en"]]
    ja_preenchida = any(planilha_esta_preenchida(p) for p in planilhas)

    if ja_preenchida:
        print("Planilha(s) de classificacao manual encontrada(s) e preenchida(s).")
        print("Pulando o BERTopic (ja rodou antes) e indo direto para o resultado final.\n")
        junta_classificacao_manual()
    else:
        print("Nenhuma planilha preenchida encontrada -- rodando BERTopic do zero.\n")
        roda_topic_modeling()
        print("\n" + "=" * 70)
        print("PROXIMO PASSO: abra as planilhas 'topicos_<idioma>_PARA_CLASSIFICAR.csv'")
        print("em " + str(SAIDA_DIR) + ", preencha 'categoria_manual' e rode este")
        print("script DE NOVO para gerar o resultado final automaticamente.")
        print("=" * 70)


if __name__ == "__main__":
    main()