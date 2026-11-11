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
| **Parte 2 — links do Reddit e vídeos** (seção 11) | 🔄 Em andamento: transcrição concluída (1.841 de 2.088); falta a análise |

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
├── basemateus/          # parte 2: links do Reddit (seção 11)
│   ├── data/            # subreddits coletados e links extraídos (Matheus)
│   ├── scripts/         # etapas 1–5 do Matheus
│   └── videosDoReddit/  # etapas 3–9: scripts/, entrada/, cache/, resultados/, transcricoes/
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

Os próximos passos da parte 2 estão na seção 11.7.

---

## 11. Parte 2 — Para onde os links do Reddit levam

> Situação em 10/11/2026. Tudo desta parte fica em `basemateus/`.

### 11.1. Objetivo

Combinado na reunião com o professor: partir dos links postados nos subreddits e
seguir o caminho **subreddit → vídeo → destino** (para onde o vídeo manda quem
assiste). Em cada ponto, olhar **toxicidade** e **monetização**. A parte 2 cruza com
o trabalho do Matheus, *Mapeando Pontes da Misoginia* (WebMedia 2026), que classifica
subreddits como pró-manosfera, anti-manosfera e interseção.

Pedidos da reunião:
- levantamento dos links por plataforma (YouTube, X, Instagram) e por comunidade;
- características dos vídeos: duração, curto × longo, títulos, curtidas, comentários;
- transcrição dos áudios, modelagem de tópicos e palavras mais citadas;
- toxicidade das transcrições;
- resumo dos vídeos por LLM, seguido de agrupamento;
- por último, tipo e preço dos cursos vendidos.

### 11.2. Pipeline

Etapas 1 e 2: scripts do Matheus, em `basemateus/scripts/`. Etapas 3 a 9: em
`basemateus/videosDoReddit/scripts/`. Os scripts acham as pastas sozinhos e rodam de
qualquer lugar. Organização de `basemateus/videosDoReddit/`:

```
videosDoReddit/
├── scripts/       # etapas 03 a 09 (.py)
├── entrada/       # youtube_links.json, youtube_videos_validos.csv
├── cache/         # respostas da API, progresso da transcrição (.jsonl) e log
├── resultados/    # todos os CSVs gerados: use estes nas análises
├── transcricoes/  # um .txt por vídeo
├── audios/        # temporário, fora do Git
└── .env           # chave da API, fora do Git
```

Não apagar `cache/`: são as respostas da API já consultadas. Sem elas, rodar de novo
gasta cota e pode trazer números diferentes.

| Etapa | Script | Saída principal | Situação |
|---|---|---|---|
| 1–2. Extrair e classificar os links dos posts | `01_extract_links.py`, `02_classify.py` | `data/0/links/02_links.jsonl` | ✅ |
| 3. Validar os vídeos do YouTube pela API | `03_validate_yotube.py` | `youtube_videos_validos.csv` | ✅ 2.088 vídeos |
| 4–5. Classificar os vídeos em blocos | `04_classifica_videos.py`, `05_agrupa_blocos.py` | `youtube_videos_blocos.csv` | ✅ |
| 6. Baixar o áudio e transcrever | `06_transcreve_videos.py` | `06_transcricoes.csv`, `transcricoes/` | ✅ 1.841 de 2.088 |
| 7. Métricas dos vídeos | `07_metricas_videos.py` | `07_youtube_metricas.csv` | ✅ 2.088 |
| 8. Linkagem e monetização | `08_linkagem.py` | `08_*.csv` | ✅ |
| 9. Normalizar as transcrições | `09_normaliza_transcricoes.py` | `09_transcricoes_normalizadas.csv` | ✅ 1.841 |

Os scripts `01` a `05` do Matheus importam `common.py`, que estava salvo como
`common copy.py`. O arquivo já foi renomeado.

Dependências extras desta parte: `ffmpeg`, Node.js e
`pip install -U yt-dlp openai-whisper spacy bertopic`.
A chave da API do YouTube fica em `basemateus/videosDoReddit/.env` (`YT_API_KEY=...`).
Esse arquivo fica fora do Git.

### 11.3. Os dados

- Links extraídos das **300 publicações de maior score** de cada um dos 1.000
  subreddits de `data/0`: 46.055 ocorrências em 810 subreddits.
- A pasta `data/1` tem outros 6.680 subreddits, mas ainda não foi usada. Falta
  confirmar com o Matheus para que ela serve.
- Vídeos válidos do YouTube: **2.088**, divididos em blocos:

| Bloco | Vídeos |
|---|---:|
| fora do recorte | 1.683 |
| manosphere/ideologia | 226 |
| autocuidado/estetica | 134 |
| looksmaxxing | 45 |

- Duração: 3 a 20 min (1.054), 1 a 3 min (401), 20 a 60 min (232), até 60 s (220),
  mais de 60 min (179). A API não informa se o vídeo é Short: a faixa de duração é
  uma aproximação.
- Mediana de 246 mil views e 5,4 mil curtidas.

### 11.4. Resultados preliminares (linkagem e monetização)

São resultados descritivos, ainda sem teste estatístico. A classificação da
monetização é feita pelo **domínio** do link, não pelo conteúdo da página.

| Bloco | Vídeos | Com link de monetização na descrição |
|---|---:|---:|
| manosphere/ideologia | 226 | 101 (45%) |
| looksmaxxing | 45 | 18 (40%) |
| autocuidado/estetica | 134 | 34 (25%) |
| fora do recorte | 1.683 | 293 (17%) |

- **Grupos do paper:** os vídeos de subreddits pró-manosfera têm monetização em 44%
  dos casos (77 de 176). Os de subreddits anti, em 35% (7 de 20, amostra pequena demais
  para comparar).
- **Destinos mais comuns:** YouTube, X/Twitter, Facebook, Instagram e Patreon.
- **Tipos de monetização:**

| Tipo | Vídeos |
|---|---:|
| Doação ou assinatura | 291 |
| Loja | 175 |
| Afiliado | 123 |
| Curso ou produto digital | 20 |

- **Nos posts:** dos 32.387 links externos postados direto no Reddit, só 2% são de
  monetização.

Cuidados ao usar esses números:
- um canal com muitos vídeos pode inflar um domínio; falta medir a concentração por canal;
- os cursos estão subestimados: só entram plataformas conhecidas, como Hotmart e Udemy;
- um link de Patreon ou de loja mostra potencial de ganho, não quanto o canal ganha;
- descrições e métricas são de hoje, não da data em que o link foi postado.

### 11.5. Transcrição (etapa 6)

- Whisper `small`, na GPU, com **tradução para o inglês** (`task="translate"`) para a
  base ficar num idioma só. O idioma original fica salvo.
- Vídeos com mais de 1 hora são pulados. O áudio é apagado depois de transcrever.
- O YouTube bloqueia a conexão depois de muitos downloads. O script espera de 30 min
  a 2 h e tenta de novo. Depois de 6 esperas seguidas, ele para: aí é só rodar de
  novo mais tarde. Vídeos que pedem login (restrição de idade) viram erro e o script
  segue.
- Resultado final: **1.841 transcritos**, 174 pulados por duração e 73 com erro de
  download definitivo: 39 com restrição de idade ou pedido de login, 29 removidos ou
  indisponíveis e 5 por outros motivos.
- **Idioma detectado errado:** o Whisper decide o idioma só pelos primeiros 30 s. Quando
  o vídeo começa com música ou silêncio, ele chuta idiomas como `nn` (norueguês, 41
  vídeos), `cy` (galês), `la`, `jw`, `mi`... e a "tradução" vira texto inventado. Em
  nov/2026, 16 desses vídeos com conteúdo real (palestras em inglês dentro do recorte,
  mais 2 em japonês e norueguês) foram refeitos com o modelo `medium` e o idioma
  forçado. 12 ficaram iguais ou melhores; 2 fora do recorte continuam ruins (Cebu City
  walk virou loop de "beep" e o vídeo do Sakurai continua sem sentido).

Refazer vídeos específicos, forçando o idioma (o registro novo substitui o antigo e
fica com `language_forced=True`; com `--idioma en` a tarefa vira `transcribe`):
```bash
python3 scripts/06_transcreve_videos.py --videos ID1,ID2 --idioma en --modelo medium
python3 scripts/09_normaliza_transcricoes.py   # depois, para atualizar a etapa 9
```

Retomar de onde parou (por exemplo, se entrarem vídeos novos em `entrada/`):
```bash
cd basemateus/videosDoReddit
setsid nohup python3 -u scripts/06_transcreve_videos.py --refazer-erros >> cache/06_transcricao.log 2>&1 &
```
Acompanhar:
```bash
ls transcricoes | wc -l                # quantos já foram transcritos
tail -c 600 cache/06_transcricao.log   # última linha da barra de progresso
pgrep -af 06_transcreve_videos         # não mostra nada quando o processo termina
```

**Rodar em paralelo** (cada pessoa na sua internet, o que também reduz o bloqueio):
todos partem do mesmo commit, e cada pessoa roda só a sua parte.
```bash
python3 scripts/06_transcreve_videos.py --refazer-erros --parte 2/3   # pessoa 2 de 3
git add cache/06_transcricoes_parte2.jsonl transcricoes/
```
No fim, uma pessoa junta tudo com `python3 scripts/06_transcreve_videos.py --so-exportar`.
Não mover nem renomear pastas enquanto a transcrição roda: o script cai.

### 11.6. Normalização (etapa 9)

`resultados/09_transcricoes_normalizadas.csv` tem duas versões de cada transcrição:

| Coluna | Como fica | Usar em |
|---|---|---|
| `texto_limpo` | frase natural (NFC, sem frases repetidas pelo Whisper) | embeddings do BERTopic, toxicidade, resumo por LLM |
| `lemas` | minúsculo, sem stopwords, lematizado (spaCy `en_core_web_sm`) | frequência de palavras, nuvem, vetorizador do BERTopic |

- As stopwords seguem o `scripts/lematiza.py`: `you`, `your`, `can`, `should` e
  outras de 2ª pessoa e de comando continuam no texto.
- Também saem muletas da fala (`yeah`, `like`, `know`, `gonna`...). Ver
  `VICIOS_DE_FALA` no script.
- Menções a dinheiro (`$100`, `20 bucks`) ficam em `valores_extraidos` e
  `menciona_valor`: 195 vídeos.
- Filtros de qualidade:
  - `low_content` (155): quase sem fala;
  - `repeticao_alta` (34): alucinação do Whisper. Marca quando mais da metade das
    frases se repete, ou quando 75% ou mais das palavras estão em sequências repetidas
    coladas ("I I I", "beep beep beep", "I'm not sure. I'm not sure"). Refrões de
    música ficam entre 0,3 e 0,5 e não são marcados (`LIMITE_LOOP` no script);
  - `idioma_suspeito` (53): idioma detectado em `IDIOMAS_SUSPEITOS` (`nn`, `cy`, `jw`,
    `sn`, `la`, `haw`, `mi`, `br`, `sa`, `yo`, `km`, `si`) e não forçado na etapa 6.
    Os 9 que estão dentro do recorte são todos vazios ou alucinação;
  - `traduzido` (297): o original não era em inglês (inclui os suspeitos).
- Base recomendada: **1.637 vídeos**, sem `low_content`, `repeticao_alta` nem
  `idioma_suspeito`. Desses, 1.410 têm fala original em inglês. Por bloco (antes do filtro): fora do recorte 1.471,
  manosphere 196, autocuidado 130, looksmaxxing 44. Sugestão: analisar os traduzidos à parte.
- Não cortar palavras curtas, como faz o pipeline do `lei_felca`: em inglês, isso
  apagaria `man`, `men`, `guy` e `sex`.

Referência de método para os próximos passos: o repositório
[estermariaa/lei_felca](https://github.com/estermariaa/lei_felca), de onde veio o
notebook de transcrição. Ele tem a configuração do BERTopic, uma lista de stopwords
do domínio, o filtro de transcrições boas e ruins, os macrotópicos e o resumo por LLM.
As transcrições de lá são de outro tema e não coincidem com os nossos vídeos.

### 11.7. Próximos passos

- [x] Terminar a transcrição e rodar `09_normaliza_transcricoes.py` de novo
- [x] Reorganizar `videosDoReddit/` em `scripts/`, `entrada/`, `cache/` e `resultados/`
- [x] Revisar idiomas detectados errado, refazer os vídeos com conteúdo e criar os
      filtros `idioma_suspeito` e loop de repetição
- [ ] Tirar à mão o `TaDhtEcX1TM` (Sakurai/Smash): continua sem sentido e passa nos filtros
- [ ] Modelagem de tópicos (BERTopic) nas transcrições e palavras mais frequentes por bloco
- [ ] Toxicidade das transcrições: Perspective API, se o Matheus tiver chave (é a mesma
      ferramenta do paper); se não tiver, Detoxify, comparando só entre os nossos grupos
- [ ] Resumo dos vídeos por LLM e agrupamento (começar por uma amostra)
- [ ] Medir a concentração da monetização por canal
- [ ] Tipo e preço dos cursos

Pendências com o Matheus:
- [ ] chave da Perspective API
- [ ] tabela de toxicidade por subreddit
- [ ] lista completa dos grupos do paper (hoje só temos 3 dos 26 subreddits de interseção)
- [ ] papel da pasta `data/1`

Limitações para o relatório:
- a unidade de análise é o vídeo inteiro, e não o post, como no paper;
- a amostra vem só das 300 publicações de maior score de cada subreddit;
- os vídeos traduzidos ficam fora da análise principal;
- a detecção de idioma do Whisper falha em vídeos que começam com música ou silêncio;
  só os vídeos com conteúdo foram refeitos à mão, o resto sai pelo `idioma_suspeito`;
- vídeos com restrição de idade não puderam ser baixados;
- os resultados só podem ser apresentados de forma agregada, por questão de ética.
