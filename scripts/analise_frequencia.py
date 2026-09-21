#!/usr/bin/env python3
"""
Analise de frequencia cruzada -- TP1 Mineracao de Dados

Cruza as colunas ja prontas do pre-processamento (bloco, menciona_valor,
views, emojis) para responder perguntas descritivas/correlacionais:

  - O bloco tematico influencia a chance de mencionar valor monetario?
  - Videos que mencionam valor tem mais views, em media?
  - A presenca de emoji varia por bloco?

Le:    <raiz>/dados/processados/videos_lematizados.csv
Salva: <raiz>/dados/processados/resultados/  (tabelas .csv + graficos .png)

Uso:
    pip3 install --break-system-packages pandas scipy matplotlib seaborn
    python3 analise_frequencia.py
"""

from pathlib import Path
import pandas as pd
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
import seaborn as sns

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA = RAIZ / "dados" / "processados" / "videos_lematizados.csv"
SAIDA_DIR = RAIZ / "dados" / "processados" / "resultados"

sns.set_theme(style="whitegrid")


def carrega():
    df = pd.read_csv(ENTRADA)
    # views vem como string as vezes (por causa do CSV) -- garante numerico
    df["views"] = pd.to_numeric(df["views"], errors="coerce")
    # menciona_valor pode ter virado string "True"/"False" ao salvar/reler CSV
    if df["menciona_valor"].dtype == object:
        df["menciona_valor"] = df["menciona_valor"].astype(str).str.lower() == "true"
    df["tem_emoji"] = df["emojis"].fillna("").astype(str).str.len() > 0
    return df.dropna(subset=["views"])


def bloco_x_menciona_valor(df):
    """Tabela de contingencia + qui-quadrado: bloco tematico influencia
    a chance de o video mencionar valor monetario/numerico?"""
    tab = pd.crosstab(df["bloco"], df["menciona_valor"])
    chi2, p, dof, _ = stats.chi2_contingency(tab)

    print("\n=== BLOCO x MENCIONA_VALOR ===")
    print(tab)
    print(f"Qui-quadrado = {chi2:.2f}, gl = {dof}, p-valor = {p:.4f}")
    if p < 0.05:
        print("-> Diferenca estatisticamente significativa entre blocos (p < 0.05).")
    else:
        print("-> Nao ha evidencia estatistica de diferenca entre blocos (p >= 0.05).")

    tab.to_csv(SAIDA_DIR / "tabela_bloco_x_menciona_valor.csv")

    prop = df.groupby("bloco")["menciona_valor"].mean().sort_values(ascending=False)
    plt.figure(figsize=(8, 5))
    sns.barplot(x=prop.values, y=prop.index, hue=prop.index, legend=False, palette="viridis")
    plt.xlabel("Proporcao de videos que mencionam valor monetario/numerico")
    plt.ylabel("Bloco tematico")
    plt.title("Mencao a valor monetario, por bloco tematico")
    plt.tight_layout()
    plt.savefig(SAIDA_DIR / "grafico_bloco_x_menciona_valor.png", dpi=150)
    plt.close()

    return chi2, p


def views_x_menciona_valor(df):
    """Compara views entre videos que mencionam valor e os que nao mencionam.
    Usa Mann-Whitney (nao-parametrico) porque views costuma ter distribuicao
    bem assimetrica -- nao e seguro assumir normalidade."""
    com_valor = df.loc[df["menciona_valor"], "views"]
    sem_valor = df.loc[~df["menciona_valor"], "views"]

    u, p = stats.mannwhitneyu(com_valor, sem_valor, alternative="two-sided")

    print("\n=== VIEWS x MENCIONA_VALOR ===")
    print(f"Mediana de views (com mencao a valor):  {com_valor.median():.0f}")
    print(f"Mediana de views (sem mencao a valor):  {sem_valor.median():.0f}")
    print(f"Mann-Whitney U = {u:.1f}, p-valor = {p:.4f}")
    if p < 0.05:
        print("-> Diferenca estatisticamente significativa (p < 0.05).")
    else:
        print("-> Nao ha evidencia estatistica de diferenca (p >= 0.05).")

    plt.figure(figsize=(7, 5))
    # log1p porque views tem outliers grandes que esmagam o grafico em escala linear
    dados_plot = df.copy()
    dados_plot["views_log"] = np.log1p(dados_plot["views"])
    sns.boxplot(data=dados_plot, x="menciona_valor", y="views_log", hue="menciona_valor",
                legend=False, palette="Set2")
    plt.xlabel("Menciona valor monetario/numerico?")
    plt.ylabel("Views (escala log)")
    plt.title("Distribuicao de views, com e sem mencao a valor")
    plt.tight_layout()
    plt.savefig(SAIDA_DIR / "grafico_views_x_menciona_valor.png", dpi=150)
    plt.close()

    return u, p


def emoji_x_bloco(df):
    """Proporcao de videos com pelo menos 1 emoji, por bloco."""
    tab = pd.crosstab(df["bloco"], df["tem_emoji"])
    chi2, p, dof, _ = stats.chi2_contingency(tab)

    print("\n=== BLOCO x TEM_EMOJI ===")
    print(tab)
    print(f"Qui-quadrado = {chi2:.2f}, gl = {dof}, p-valor = {p:.4f}")

    prop = df.groupby("bloco")["tem_emoji"].mean().sort_values(ascending=False)
    plt.figure(figsize=(8, 5))
    sns.barplot(x=prop.values, y=prop.index, hue=prop.index, legend=False, palette="magma")
    plt.xlabel("Proporcao de videos com pelo menos 1 emoji")
    plt.ylabel("Bloco tematico")
    plt.title("Uso de emoji em titulo/descricao, por bloco tematico")
    plt.tight_layout()
    plt.savefig(SAIDA_DIR / "grafico_bloco_x_emoji.png", dpi=150)
    plt.close()

    return chi2, p


def resumo_geral(df):
    """Tabela resumo por bloco: n, % com valor, mediana de views, % com emoji.
    Boa para colar direto numa tabela do relatorio."""
    resumo = df.groupby("bloco").agg(
        n_videos=("video_id", "count") if "video_id" in df.columns else ("bloco", "count"),
        pct_menciona_valor=("menciona_valor", "mean"),
        mediana_views=("views", "median"),
        pct_tem_emoji=("tem_emoji", "mean"),
    ).round(3).sort_values("n_videos", ascending=False)

    print("\n=== RESUMO GERAL POR BLOCO ===")
    print(resumo)
    resumo.to_csv(SAIDA_DIR / "resumo_geral_por_bloco.csv")
    return resumo


def main():
    if not ENTRADA.exists():
        raise SystemExit(f"Nao encontrei {ENTRADA}. Rode o pre-processamento antes.")

    SAIDA_DIR.mkdir(parents=True, exist_ok=True)
    df = carrega()
    print(f"Base carregada: {len(df)} videos com views validas.")

    resumo_geral(df)
    bloco_x_menciona_valor(df)
    views_x_menciona_valor(df)
    emoji_x_bloco(df)

    print(f"\nTudo salvo em: {SAIDA_DIR}")
    print("(tabelas .csv + graficos .png prontos para colar no relatorio)")


if __name__ == "__main__":
    main()