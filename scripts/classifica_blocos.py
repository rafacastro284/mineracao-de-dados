#!/usr/bin/env python3
"""
Passo 1 da mineracao -- limpeza leve do termo_busca + classificacao em blocos.

Le:    <raiz>/dados/processados/videos_limpos.csv
Salva: <raiz>/dados/processados/videos_classificados.csv

O que faz:
  - normaliza 'termo_busca' (minusculo + sem espacos nas pontas) para juntar
    variacoes de caixa (ex.: "Rain Santos" e "rain santos" viram o mesmo termo);
  - descarta linhas corrompidas (termo vazio ou invalido, ex.: "pt");
  - cria a coluna 'bloco', agrupando os termos em quatro eixos tematicos:
    autocuidado/estetica, looksmaxxing, manosphere/ideologia, criadores_pt;
  - cria a coluna 'categoria' (nome legivel a partir do categoria_id do YouTube).

Rode de qualquer pasta:
    python3 classifica_blocos.py
"""

from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent   # scripts/ -> raiz do projeto
ENTRADA = RAIZ / "dados" / "processados" / "videos_limpos.csv"
SAIDA = RAIZ / "dados" / "processados" / "videos_classificados.csv"

# termos que nao sao busca real (corrompidos) -> descartar
TERMOS_INVALIDOS = {"", "nan", "none", "pt", "en"}

# categorias oficiais do YouTube (id -> nome legivel, em portugues)
CATEGORIAS_YT = {
    1: "Filme e Animacao", 2: "Automoveis", 10: "Musica", 15: "Animais e Pets",
    17: "Esporte", 18: "Curtas", 19: "Viagem e Eventos", 20: "Jogos",
    21: "Videoblog", 22: "Pessoas e Blogs", 23: "Comedia", 24: "Entretenimento",
    25: "Noticias e Politica", 26: "Moda e Estilo", 27: "Educacao",
    28: "Ciencia e Tecnologia", 29: "ONGs e Ativismo", 30: "Filmes",
    43: "Programas", 44: "Trailers",
}


def nome_categoria(cid):
    """Converte o categoria_id numerico do YouTube no nome legivel."""
    try:
        cid = int(float(cid))
    except (ValueError, TypeError):
        return "Desconhecida"
    return CATEGORIAS_YT.get(cid, f"Outra (id {cid})")


def classificar(termo):
    """Mapeia um termo de busca (ja em minusculo) para um bloco tematico."""
    t = str(termo)
    # criadores (nomes proprios) primeiro, para nao se confundir com palavras genericas
    if any(k in t for k in ["thiago nigro", "gabriel breier", "breno faria", "rain santos"]):
        return "criadores_pt"
    if any(k in t for k in ["alpha", "awalt", "high-value", "high value",
                            "supremac", "mindset for men", "andrew tate"]):
        return "manosphere/ideologia"
    if any(k in t for k in ["looksmax", "mewing", "softmax", "hardmax"]):
        return "looksmaxxing"
    if any(k in t for k in ["skincare", "grooming", "barba", "dermatolog", "glow up",
                            "autocuidado", "cuidados", "self care", "self-care",
                            "se cuidando"]):
        return "autocuidado/estetica"
    return "indefinido"


def main():
    if not ENTRADA.exists():
        raise SystemExit(f"Nao encontrei {ENTRADA}. Rode a limpeza antes.")

    df = pd.read_csv(ENTRADA, on_bad_lines="skip", engine="python")
    n0 = len(df)

    # 1) descarta linhas sem termo de busca (NaN -> corrompidas/restos de merge)
    df = df.dropna(subset=["termo_busca"]).copy()

    # 2) normaliza o termo de busca (junta variacoes de caixa)
    df["termo_busca"] = df["termo_busca"].astype(str).str.lower().str.strip()

    # 3) descarta linhas com termo invalido/corrompido (ex.: "pt")
    df = df[~df["termo_busca"].isin(TERMOS_INVALIDOS)].copy()
    n_descartados = n0 - len(df)

    # 4) classifica em blocos
    df["bloco"] = df["termo_busca"].map(classificar)

    # 5) categoria legivel a partir do categoria_id do YouTube
    df["categoria"] = df["categoria_id"].map(nome_categoria)

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SAIDA, index=False)

    print(f"Base lida:      {n0} videos")
    print(f"Descartados:    {n_descartados} (termo invalido/corrompido)")
    print(f"Base final:     {len(df)} videos  ->  {SAIDA.name}")
    print(f"Termos unicos apos normalizar a caixa: {df['termo_busca'].nunique()}")
    print("\n== VIDEOS POR BLOCO ==")
    print(df["bloco"].value_counts().to_string())
    print("\n== VIDEOS POR CATEGORIA (YouTube) ==")
    print(df["categoria"].value_counts().to_string())

    indef = df.loc[df["bloco"] == "indefinido", "termo_busca"].value_counts()
    if len(indef):
        print("\n(termos que ficaram 'indefinido' -- conferir/ajustar o mapa:)")
        print(indef.to_string())


if __name__ == "__main__":
    main()