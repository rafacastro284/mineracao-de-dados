# Mineração de Dados — Do autocuidado ao manosphere no YouTube

Trabalho Prático 1 da disciplina de **Mineração de Dados**.
Estudo de caso que coleta e minera vídeos do YouTube sobre o **conteúdo masculino**,
num espectro que vai do **autocuidado/estética** (skincare, grooming, glow up,
looksmaxxing) até o discurso de **masculinidade/manosphere** (alpha male,
high-value man, etc.). O objetivo é entender como esse universo se organiza, quais
temas engajam mais e como evolui no tempo — dialogando com a discussão sobre o
cuidado pessoal como porta de entrada ("softmaxxing") de um funil maior.

- **Apresentações:** 22/09/2026 e 24/09/2026
- **Base atual:** 9.699 vídeos (PT + EN), limpos, classificados e lematizados
- **Fonte dos dados:** YouTube Data API v3 (coleta própria)

> Guia detalhado do projeto (pipeline, reprodução, metodologia): ver `GUIA_DO_PROJETO.md`.

---

## Status atual

| Etapa | Situação |
|-------|----------|
| Coleta de vídeos | ✅ Feita — 9.699 vídeos |
| Pré-processamento / limpeza | ✅ Feito |
| Classificação em blocos + categoria legível | ✅ Feito |
| Lematização (PLN) de títulos + descrições | ✅ Feito |
| Coleta de comentários | ✅ Feita — 177.640 comentários — ⬜ falta anonimizar `autor` e usar na análise |
| Mineração — engajamento por bloco/idioma/ano | ✅ Feito |
| Mineração — evolução temporal por bloco | ✅ Feito |
| Mineração — comparação estatística PT × EN | ✅ Feito |
| Mineração — agrupamento / topic modeling (BERTopic) | ⬜ Rodado, falta preencher a classificação manual dos tópicos |
| Levantamento de literatura | ⬜ A fazer |
| Relatório (LaTeX) | ⬜ A fazer |
| Apresentação | ⬜ A fazer |

**A base final para a mineração é `dados/processados/videos_lematizados.csv`.**
**Os resultados da mineração ficam em `dados/processados/resultados/`.**

---

## Estrutura do projeto

```
mineracao-de-dados/
├── dados/
│   ├── brutos/          # dado cru da API (NÃO editar na mão)
│   │   ├── videos_masculino.csv
│   │   └── comentarios.csv        (após rodar o coletor de comentários)
│   └── processados/     # dado tratado, usado na mineração
│       ├── videos_limpos.csv
│       ├── videos_classificados.csv
│       ├── videos_lematizados.csv   <- base final
│       ├── resumo_termos.csv
│       ├── videos_por_ano.csv
│       └── resultados/  # tabelas .csv + gráficos .png da mineração
├── scripts/
│   ├── coletor_youtube.py     # coleta metadados dos vídeos (acumula)
│   ├── coletor_comentarios.py # coleta comentários dos vídeos
│   ├── limpeza.py             # gera a base limpa
│   ├── classifica_blocos.py   # cria as colunas 'bloco' e 'categoria'
│   ├── lematiza.py            # lematiza títulos+descrições (spaCy PT/EN)
│   ├── resumo_termos.py       # relatórios de apoio (termos, por ano)
│   ├── analise_frequencia.py  # mineração: cruzamentos, engajamento, evolução temporal, PT×EN
│   └── bertopics.py           # mineração: topic modeling (BERTopic) por idioma
├── notebooks/           # exploração e mineração
├── relatorio/           # relatório em LaTeX
├── README.md
└── GUIA_DO_PROJETO.md
```

**Regra de ouro:** dado bruto nunca é editado na mão. Todo tratamento é feito por
script, gerando uma cópia em `dados/processados/`.

---

## Como rodar

### Pré-requisitos
```
pip3 install --break-system-packages google-api-python-client pandas python-dotenv spacy
python3 -m spacy download pt_core_news_sm
python3 -m spacy download en_core_web_sm
```
Se o `spacy download` reclamar de "externally-managed-environment", instale os
modelos direto (ver `GUIA_DO_PROJETO.md`).

### Chave da API
Só necessária para **coletar**. Cada integrante usa a **sua própria** chave da
YouTube Data API v3 (gratuita, sem cartão), num `.env` dentro de `scripts/`
(o `.gitignore` já ignora):
```
YT_API_KEY=SUA_CHAVE_AQUI
```

### Ordem de execução
```
python3 scripts/coletor_youtube.py       # 1. coleta/atualiza os vídeos (precisa de chave)
python3 scripts/limpeza.py               # 2. gera a base limpa
python3 scripts/classifica_blocos.py     # 3. cria 'bloco' e 'categoria'
python3 scripts/lematiza.py              # 4. cria 'lemas'
python3 scripts/analise_frequencia.py    # 5. mineração: cruzamentos, engajamento, evolução, PT×EN
python3 scripts/bertopics.py             # 6. mineração: topic modeling (rodar 2x, ver script)
```
Quem só vai **minerar** nem precisa coletar: um `git pull` e usar o
`videos_lematizados.csv`. Os caminhos são resolvidos automaticamente.

---

## Dicionário de dados (`videos_lematizados.csv`)

| Coluna | Descrição |
|--------|-----------|
| `video_id` | ID único do vídeo no YouTube |
| `titulo` / `descricao` | textos do vídeo (emojis e acentos preservados) |
| `canal` | nome do canal |
| `publicado_em` / `ano` | data de publicação (UTC) e ano |
| `categoria_id` / `categoria` | categoria do YouTube (código e nome legível) |
| `idioma_video` | idioma declarado pelo canal |
| `tags` | tags do vídeo, separadas por `\|` |
| `duracao_iso` / `duracao_seg` | duração (ISO 8601 e em segundos) |
| `views` / `likes` / `comentarios` | métricas (likes/comentários podem estar ocultos) |
| `termo_busca` / `idioma_termo` | termo e idioma da busca que trouxe o vídeo |
| `bloco` | eixo temático: autocuidado/estetica, looksmaxxing, manosphere/ideologia, criadores_pt |
| `lemas` | títulos + descrições lematizados (para mineração de texto) |

`comentarios.csv`: `comment_id`, `video_id`, `autor`, `texto`, `likes`, `publicado_em`, `respostas`.

---

## Resultados da mineração (`dados/processados/resultados/`)

Gerados por `analise_frequencia.py`:
- `resumo_geral_por_bloco.csv` — n, % menciona valor, mediana de views, % emoji, por bloco
- `tabela_bloco_x_menciona_valor.csv`, `grafico_bloco_x_menciona_valor.png`
- `grafico_views_x_menciona_valor.png`, `grafico_bloco_x_emoji.png`, `grafico_views_entre_blocos.png`
- `engajamento_por_bloco.csv` / `engajamento_por_idioma.csv` (só PT/EN) / `engajamento_por_ano.csv`
- `concentracao_por_canal.csv`
- `evolucao_temporal.csv`, `grafico_evolucao_temporal.png` — % menciona valor ao longo dos anos, uma linha por bloco
- `comparacao_pt_en.csv` — comparação estatística PT × EN (menção a valor: qui-quadrado; engajamento: Mann-Whitney)

Gerados por `bertopics.py` (topic modeling por idioma):
- `topicos_pt.csv` / `topicos_en.csv`, `topicos_pt_resumo.csv` / `topicos_en_resumo.csv`
- `topicos_pt_PARA_CLASSIFICAR.csv` / `topicos_en_PARA_CLASSIFICAR.csv` — **preencher `categoria_manual` à mão** e rodar o script de novo para gerar `videos_com_categoria_topico.csv`
- `grafico_topicos_pt.png` / `grafico_topicos_en.png`, `topicos_pt_barchart.html` / `topicos_en_barchart.html`, `topicos_pt_mapa.html` / `topicos_en_mapa.html`

---

## Decisões e observações

- **Coleta acumulativa:** o coletor não sobrescreve; lê a base e só adiciona vídeos
  inéditos. Dá pra crescer a base variando o `ORDER` (`relevance`/`viewCount`/`date`).
- **Cota da API:** ~10.000 unidades/dia. Busca custa 100; comentário, 1. Se esgotar,
  os scripts param e retomam no dia seguinte.
- **Limpeza:** normaliza texto (NFC), remove só invisíveis órfãos e **preserva emojis
  e acentos**.
- **Blocos:** a classificação é pelo termo de busca (1ª camada); será validada/
  complementada por agrupamento automático na mineração.
- **Lematização:** por idioma (spaCy PT/EN). O modelo PT (`sm`) erra em gíria
  ("rotina"→"rotino") — limitação conhecida, aceitável para agrupar temas.
- **Faltantes respeitados:** descrição/tags vazias e likes ocultos **não são
  imputados**.
- **Privacidade (comentários):** descartar/anonimizar a coluna `autor` na análise.

---

## Próximos passos (dividir entre o time)

- [ ] Preencher `categoria_manual` nas planilhas do BERTopic e rodar `bertopics.py` de novo
- [ ] (Opcional) Anonimizar `autor` em `comentarios.csv` e usar os comentários na análise
- [ ] Levantar 2–4 trabalhos recentes da literatura sobre o tema
- [ ] Escrever o relatório (LaTeX)
- [ ] Montar a apresentação

## Integrantes
Bárbara
Caren
Rafael