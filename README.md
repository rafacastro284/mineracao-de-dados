# Mineração de Dados — Que vídeos as comunidades da manosfera no Reddit compartilham

Trabalho da disciplina de **Mineração de Dados**. Partimos da base de subreddits do
artigo do Matheus, *Mapeando Pontes da Misoginia* (WebMedia 2026), para descobrir
**que tipos de vídeos essas comunidades compartilham** e para onde esses vídeos levam
quem assiste.

**Como a base foi construída:**
1. **Subreddits do artigo:** os 1.000 subreddits com mais variedade de palavras-chave
   da manosfera, com as 300 publicações de maior score de cada um.
2. **Links compartilhados:** extraímos os links dos posts e classificamos por
   plataforma. Fora o próprio Reddit, o YouTube é o destino externo mais comum.
3. **Vídeos do YouTube:** coletamos os links que levam ao YouTube e validamos os vídeos
   pela API (2.088 válidos), com métricas, blocos temáticos e os links das descrições
   (monetização).
4. **Transcrição:** baixamos o áudio e transcrevemos os vídeos com o Whisper, depois
   normalizamos o texto para a análise. Transcrevemos porque título e descrição mostram
   como o vídeo se apresenta, não o que ele diz: o texto falado é a base da modelagem
   de tópicos, da toxicidade e dos resumos.

**Transcrição: 1.841 de 2.088 vídeos (88%, cerca de 284 h de áudio).** Os 247 que
ficaram de fora:

| Motivo | Vídeos |
|---|---:|
| Mais de 1 hora (pulados de propósito: lives, podcasts e transmissões longas) | 173 |
| Restrição de idade ou pedido de login | 39 |
| Removido, privado ou indisponível | 19 |
| Bloqueado por direitos autorais | 6 |
| Live em andamento ou gravação de live indisponível | 5 |
| Só para membros do canal | 2 |
| Outros (bloqueio regional, HTTP 403) | 3 |

Depois dos filtros de qualidade (vídeos quase sem fala, alucinações do Whisper e
idioma detectado errado), a base recomendada para análise tem **1.637 vídeos**. Por
bloco, no guia (seção 7).

Em cada ponto do caminho **subreddit → vídeo → destino**, a análise olha
**toxicidade** e **monetização**, comparando os grupos do artigo (pró-manosfera,
anti-manosfera e interseção).

- **Fontes dos dados:** base de subreddits do artigo do Matheus (Reddit) e YouTube
  Data API v3
- **Base principal:** `basemateus/videosDoReddit/resultados/09_transcricoes_normalizadas.csv`
  (1.841 transcrições; base recomendada para análise: 1.637)

> Guia detalhado (pipeline, reprodução, decisões e o trabalho anterior):
> ver `GUIA_DO_PROJETO.md`.

---

## Status atual

| Etapa | Situação |
|-------|----------|
| Subreddits do artigo e extração dos links dos posts | ✅ Feita — 46.055 ocorrências em 810 subreddits |
| Validação dos vídeos do YouTube pela API | ✅ Feita — 2.088 vídeos |
| Classificação dos vídeos em blocos | ✅ Feita |
| Transcrição dos vídeos | ✅ Feita — 1.841 de 2.088 |
| Métricas, linkagem e monetização | ✅ Feita |
| Normalização das transcrições | ✅ Feita |
| Métricas de áudio e de fala | ✅ Feita (sem baixar os áudios de novo) |
| Tópicos, palavras mais frequentes, toxicidade, resumo por LLM | ⬜ A fazer |
| Levantamento de literatura | ⬜ A fazer |
| Relatório (LaTeX) | ⬜ A fazer |
| Apresentação | ⬜ A fazer |

---

## Estrutura do projeto

```
mineracao-de-dados/
├── basemateus/                 # projeto atual
│   ├── data/                   # subreddits do artigo e links extraídos (Matheus)
│   ├── scripts/                # etapas 1–2: extrair e classificar os links dos posts
│   └── videosDoReddit/
│       ├── scripts/            # etapas 3–9: validar, classificar, transcrever, métricas, linkagem, normalizar
│       ├── entrada/            # links do YouTube e vídeos válidos
│       ├── cache/              # respostas da API e progresso da transcrição (não apagar)
│       ├── resultados/         # CSVs gerados: use estes nas análises
│       └── transcricoes/       # um .txt por vídeo
├── dados/ e scripts/           # trabalho anterior (TP1): coleta por busca no YouTube
├── notebooks/
├── relatorio/                  # relatório em LaTeX
├── README.md
└── GUIA_DO_PROJETO.md
```

---

## Como rodar

### Pré-requisitos
```
sudo apt install ffmpeg nodejs
pip3 install -U pandas requests python-dotenv sentence-transformers yt-dlp openai-whisper spacy bertopic
python3 -m spacy download en_core_web_sm
```

### Chave da API
Só necessária para consultar a API do YouTube (etapas 3, 4 e 7). Fica em
`basemateus/videosDoReddit/.env`, fora do Git:
```
YT_API_KEY=SUA_CHAVE_AQUI
```

### Ordem de execução
```
python3 basemateus/scripts/01_extract_links.py                  # 1. links dos posts
python3 basemateus/scripts/02_classify.py                       # 2. classifica por plataforma
python3 basemateus/videosDoReddit/scripts/03_validate_yotube.py # 3. valida os vídeos (API)
python3 basemateus/videosDoReddit/scripts/04_classifica_videos.py
python3 basemateus/videosDoReddit/scripts/05_agrupa_blocos.py   # 4–5. blocos temáticos
python3 basemateus/videosDoReddit/scripts/06_transcreve_videos.py   # 6. áudio + Whisper (demorado)
python3 basemateus/videosDoReddit/scripts/07_metricas_videos.py # 7. métricas (API)
python3 basemateus/videosDoReddit/scripts/08_linkagem.py        # 8. destinos e monetização
python3 basemateus/videosDoReddit/scripts/09_normaliza_transcricoes.py  # 9. texto limpo e lemas
python3 basemateus/videosDoReddit/scripts/10_metricas_audio.py  # 10. métricas de fala (análise em notebooks/)
```
Quem só vai analisar não precisa rodar nada: um `git pull` e usar os CSVs de
`basemateus/videosDoReddit/resultados/`. Detalhes de cada etapa (retomar a
transcrição, rodar em paralelo, refazer vídeos) estão no guia.

---

## Principais arquivos de resultado (`basemateus/videosDoReddit/resultados/`)

| Arquivo | Conteúdo |
|---|---|
| `youtube_videos_blocos.csv` | vídeos válidos com bloco temático, canal e subreddits de origem |
| `06_transcricoes.csv` | status, idioma e transcrição bruta de cada vídeo |
| `07_youtube_metricas.csv` | views, curtidas, comentários e duração |
| `08_video_destinos.csv`, `08_dominios_classificados.csv` | links das descrições e tipo de monetização |
| `08_subreddit_resumo.csv`, `08_subreddit_dominio.csv` | resumo por subreddit |
| `09_transcricoes_normalizadas.csv` | `texto_limpo`, `lemas` e filtros de qualidade (`low_content`, `repeticao_alta`, `idioma_suspeito`) |
| `10_metricas_audio.csv` | duração, palavras por minuto, cobertura e ritmo da fala; análise em `notebooks/10_metricas_audio.ipynb` |

---

## Próximos passos

- [ ] Modelagem de tópicos (BERTopic) nas transcrições e palavras mais frequentes por bloco
- [ ] Toxicidade das transcrições (Perspective API ou Detoxify)
- [ ] Resumo dos vídeos por LLM e agrupamento
- [ ] Concentração da monetização por canal; tipo e preço dos cursos
- [ ] Levantar 2–4 trabalhos recentes da literatura
- [ ] Escrever o relatório (LaTeX) e montar a apresentação

---

## Trabalho anterior (TP1): coleta por busca no YouTube

Antes da base do Reddit, o grupo coletou **9.699 vídeos (PT + EN)** pela busca de
termos na API do YouTube, num espectro que vai do autocuidado/estética ao discurso
de manosphere, com 177.640 comentários. Essa base foi limpa, classificada em blocos,
lematizada e minerada (engajamento, evolução temporal, PT × EN e BERTopic).

- Base: `dados/processados/videos_lematizados.csv`; resultados em
  `dados/processados/resultados/`; scripts em `scripts/`.
- Ordem: `coletor_youtube.py` → `limpeza.py` → `classifica_blocos.py` →
  `lematiza.py` → `analise_frequencia.py` → `bertopics.py`.
- Pendente: preencher `categoria_manual` nas planilhas `topicos_*_PARA_CLASSIFICAR.csv`.
- Pipeline, dicionário de dados e decisões: seção 11 do `GUIA_DO_PROJETO.md`.

---

## Integrantes
Bárbara
Caren
Rafael