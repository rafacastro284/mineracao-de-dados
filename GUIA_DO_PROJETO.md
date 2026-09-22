# Guia do Projeto — TP1 Mineração de Dados

> Documento para alinhar o grupo: o que já foi feito, como a base foi construída,
> como reproduzir tudo do zero e o que ainda falta. Complementa o `README.md`.

---

## 1. Sobre o projeto

Estudo de caso de mineração de dados sobre **o conteúdo masculino no YouTube**,
que vai do **autocuidado/estética** (skincare, grooming, looksmaxxing) até o
discurso de **masculinidade/manosphere** (alpha male, high-value man, etc.).

A ideia é entender como esse universo se organiza — quais temas existem, quais
engajam mais, como evoluíram no tempo e como se diferenciam entre Brasil e mundo
anglófono. O recorte dialoga com o relatório *The Grift Economy* (Reset Tech &
Equimundo, 2026), que descreve o cuidado pessoal ("softmaxxing") como porta de
entrada de um funil que leva ao looksmaxxing e, adiante, ao manosphere.

- **Disciplina:** Mineração de Dados (TP1)
- **Apresentações:** 22 e 24/09/2026
- **Fonte dos dados:** YouTube Data API v3 (coleta própria)
- **Ferramentas:** Python, pandas, spaCy

---

## 2. Estado atual

| Etapa | Situação |
|-------|----------|
| Coleta de vídeos | ✅ Feita — 9.699 vídeos (PT + EN) |
| Limpeza / pré-processamento | ✅ Feita |
| Classificação em blocos + categoria legível | ✅ Feita |
| Lematização (PLN) de títulos + descrições | ✅ Feita |
| Coleta de comentários | ✅ Feita — 177.640 comentários — ⬜ falta anonimizar `autor` e usar na análise |
| Mineração — engajamento por bloco/idioma/ano | ✅ Feita |
| Mineração — evolução temporal por bloco | ✅ Feita |
| Mineração — comparação estatística PT × EN | ✅ Feita |
| Mineração — agrupamento / topic modeling (BERTopic) | ⬜ Rodado, falta preencher a classificação manual dos tópicos |
| Levantamento de literatura | ⬜ A fazer |
| Relatório (LaTeX) | ⬜ A fazer |
| Apresentação | ⬜ A fazer |

---

## 3. A base hoje (em números)

- **9.699 vídeos únicos**, sem duplicatas.
- Idioma: **~4.970 PT** e **~4.730 EN**.
- Dividida em quatro **blocos temáticos**:

| Bloco | Vídeos |
|-------|--------|
| manosphere/ideologia | 2.959 |
| autocuidado/estética | 2.843 |
| criadores_pt | 2.276 |
| looksmaxxing | 1.621 |

- **Achados preliminares** (já úteis pro relatório):
  - A produção explode a partir de 2021–2022 e cresce forte até 2025–2026.
  - Engajamento (mediana de views) por bloco: **looksmaxxing (~198 mil) > autocuidado
    (~93 mil) > manosphere (~27 mil) > criadores (~16 mil)** — conteúdo de aparência
    viraliza bem mais que o ideológico.
  - Categorias dominantes: Pessoas e Blogs, Educação, Entretenimento, Moda e Estilo.

---

## 4. O pipeline (scripts, na ordem)

Todos os scripts ficam em `scripts/` e resolvem os caminhos sozinhos (rodam de
qualquer pasta). A ordem lógica é:

1. **`coletor_youtube.py`** — busca metadados de vídeos na YouTube Data API a
   partir de uma lista de termos (PT + EN). É **acumulativo**: lê o CSV existente
   e só adiciona vídeos inéditos.
   → gera/atualiza `dados/brutos/videos_masculino.csv`

2. **`limpeza.py`** — normaliza o texto (NFC, remove caracteres invisíveis órfãos,
   preserva emojis/acentos), cria as colunas `ano` e `duracao_seg`.
   → `dados/brutos/videos_masculino.csv` → `dados/processados/videos_limpos.csv`

3. **`classifica_blocos.py`** — normaliza o `termo_busca` (junta variações de
   caixa), descarta linhas corrompidas, e cria as colunas `bloco` (eixo temático)
   e `categoria` (nome legível da categoria do YouTube).
   → `videos_limpos.csv` → `dados/processados/videos_classificados.csv`

4. **`lematiza.py`** — pré-processa e **lematiza** títulos + descrições com spaCy
   (PT com `pt_core_news_sm`, EN com `en_core_web_sm`), gerando a coluna `lemas`.
   → `videos_classificados.csv` → `dados/processados/videos_lematizados.csv`

5. **`resumo_termos.py`** *(apoio)* — gera relatórios da base: termos de busca com
   contagem/período e vídeos por ano.
   → `dados/processados/resumo_termos.csv` e `videos_por_ano.csv`

6. **`coletor_comentarios.py`** *(opcional, já rodado)* — coleta os
   comentários de cada vídeo. É **resumível** e para sozinho se a cota acabar.
   → `dados/brutos/comentarios.csv` (177.640 comentários)

7. **`analise_frequencia.py`** — a mineração propriamente dita: cruzamentos
   (bloco × menção a valor, bloco × emoji), views entre blocos (Kruskal-Wallis),
   engajamento (likes/comentários por views) aberto por bloco/idioma/ano,
   concentração por canal, evolução temporal por bloco e comparação estatística
   PT × EN (qui-quadrado + Mann-Whitney).
   → `videos_lematizados.csv` → `dados/processados/resultados/*.csv` e `*.png`

8. **`bertopics.py`** — topic modeling (BERTopic) sobre a coluna `lemas`, por
   idioma (pt/en). Roda em duas etapas: 1ª gera as planilhas
   `topicos_<idioma>_PARA_CLASSIFICAR.csv` para preenchimento manual da coluna
   `categoria_manual`; 2ª (rodar de novo após preencher) junta essa classificação
   na base inteira, gerando `videos_com_categoria_topico.csv`.
   → `videos_lematizados.csv` → `dados/processados/resultados/topicos_*` (⬜ classificação manual ainda não preenchida)

**A base final para a mineração é `dados/processados/videos_lematizados.csv`.**
**Os resultados da mineração ficam em `dados/processados/resultados/`.**

---

## 5. Como reproduzir do zero

### 5.1. Dependências (uma vez)
```
pip3 install --break-system-packages google-api-python-client pandas python-dotenv spacy
python3 -m spacy download pt_core_news_sm
python3 -m spacy download en_core_web_sm
```
Se o `spacy download` reclamar de "externally-managed-environment", instale os
modelos direto:
```
pip3 install --break-system-packages \
  "https://github.com/explosion/spacy-models/releases/download/pt_core_news_sm-3.8.0/pt_core_news_sm-3.8.0-py3-none-any.whl" \
  "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
```

### 5.2. Chave da API
Só necessária para **coletar** (não para reprocessar a base já commitada). Cada
integrante usa a **sua própria** chave da YouTube Data API v3 (gratuita, sem
cartão), num arquivo `.env` dentro de `scripts/` (o `.gitignore` já ignora):
```
YT_API_KEY=SUA_CHAVE_AQUI
```

### 5.3. Rodar (de dentro de `scripts/`)
```
python3 limpeza.py               # se mexeu na base bruta
python3 classifica_blocos.py
python3 lematiza.py
python3 analise_frequencia.py    # mineração: cruzamentos, engajamento, evolução, PT×EN
python3 bertopics.py             # mineração: topic modeling (rodar 2x, ver seção 4)
```
Se a base já está commitada, quem só vai **minerar** nem precisa rodar a coleta:
basta um `git pull` e usar o `videos_lematizados.csv`.

---

## 6. Estrutura de pastas

```
mineracao-de-dados/
├── dados/
│   ├── brutos/          # dado cru da API (NÃO editar na mão)
│   │   ├── videos_masculino.csv
│   │   └── comentarios.csv
│   └── processados/     # dado tratado, usado na mineração
│       ├── videos_limpos.csv
│       ├── videos_classificados.csv
│       ├── videos_lematizados.csv   <- base final
│       ├── resumo_termos.csv
│       ├── videos_por_ano.csv
│       └── resultados/  # tabelas .csv + gráficos .png da mineração
├── scripts/
│   ├── coletor_youtube.py
│   ├── coletor_comentarios.py
│   ├── limpeza.py
│   ├── classifica_blocos.py
│   ├── lematiza.py
│   ├── resumo_termos.py
│   ├── analise_frequencia.py
│   └── bertopics.py
├── notebooks/           # exploração (a fazer)
├── relatorio/           # LaTeX (a fazer)
├── README.md
└── GUIA_DO_PROJETO.md
```

---

## 7. Dicionário de dados (`videos_lematizados.csv`)

| Coluna | Descrição |
|--------|-----------|
| `video_id` | ID único do vídeo |
| `titulo` / `descricao` | textos originais (emojis/acentos preservados) |
| `canal` | nome do canal |
| `publicado_em` / `ano` | data de publicação (UTC) e ano |
| `categoria_id` / `categoria` | categoria do YouTube (código e nome legível) |
| `idioma_video` | idioma declarado pelo canal |
| `tags` | tags do vídeo (separadas por `\|`) |
| `duracao_iso` / `duracao_seg` | duração em ISO 8601 e em segundos |
| `views` / `likes` / `comentarios` | métricas (likes/comentários podem estar ocultos) |
| `termo_busca` / `idioma_termo` | termo e idioma da busca que trouxe o vídeo |
| `bloco` | eixo temático: autocuidado/estetica, looksmaxxing, manosphere/ideologia, criadores_pt |
| `lemas` | títulos + descrições lematizados (para mineração de texto) |

---

## 8. Decisões metodológicas (levar pro relatório)

- **Coleta própria (não UCI/Kaggle):** não existe dataset pronto para esse recorte;
  a coleta via API é justificada e documentada.
- **Coleta acumulativa + deduplicação por `video_id`:** permite crescer a base em
  várias rodadas sem repetição.
- **Preservação de emojis e acentos:** são informação do conteúdo; só removemos
  caracteres invisíveis realmente órfãos (o ZWJ de emojis compostos é mantido).
- **Valores ausentes respeitados:** descrição/tags vazias e likes ocultos **não são
  imputados** — preencher seria inventar dado.
- **Classificação em blocos pelo termo de busca:** é uma primeira camada (rótulo do
  "assunto que trouxe o vídeo"); será **validada/complementada por agrupamento
  automático** (topic modeling) na mineração.
- **Lematização:** feita por idioma (spaCy PT/EN). O modelo PT (`sm`) erra em gíria
  ("rotina"→"rotino") — limitação conhecida, aceitável para agrupar temas.
- **Ruído de descrição:** há boilerplate promocional (links, "instagram/tiktok/shop")
  — na etapa de topic modeling vamos usar uma lista de **stopwords customizadas**.
- **Privacidade (comentários):** ao usar comentários, descartar/anonimizar a coluna
  `autor` e trabalhar só com o texto.

---

## 9. Combinado de trabalho em grupo

Para evitar bases diferentes e conflitos de merge:

- **Uma pessoa é responsável pela coleta** — roda o coletor e commita a base.
  Os demais só dão `git pull` e trabalham em cima da **mesma** base.
- **A base é versionada no Git** (é pequena), para todos partirem do mesmo ponto.
- Se houver conflito num CSV, resolver **unindo e deduplicando por `video_id`**
  (não mesclar linha a linha).
- Cada pessoa usa a **sua própria chave de API** (no `.env`, fora do Git).

---

## 10. Próximos passos (dividir entre o time)

- [ ] **Preencher `categoria_manual`** nas planilhas `topicos_<idioma>_PARA_CLASSIFICAR.csv`
      (BERTopic) e rodar `bertopics.py` de novo para gerar `videos_com_categoria_topico.csv`
- [ ] (Opcional) Anonimizar a coluna `autor` em `comentarios.csv` e usar os
      comentários na análise
- [ ] Levantar 2–4 trabalhos recentes da literatura (manosphere / looksmaxxing /
      cuidado masculino)
- [ ] Escrever o relatório em LaTeX
- [ ] Montar a apresentação