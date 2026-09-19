# Mineração de Dados — A nova onda de cuidado masculino no YouTube

Trabalho Prático 1 da disciplina de **Mineração de Dados**.
Estudo de caso que coleta e minera vídeos do YouTube sobre a **nova onda de
cuidado / embelezamento masculino** (skincare, grooming, glow up, looksmaxxing),
para entender como o tema se organiza, quais assuntos engajam mais e como isso
dialoga com a discussão sobre autocuidado masculino como porta de entrada
("softmaxxing").

- **Apresentações:** 22/09/2026 e 24/09/2026
- **Base coletada até agora:** 2917 vídeos (PT + EN), já limpos
- **Fonte dos dados:** YouTube Data API v3 (coleta própria)

---

## Status atual

| Etapa | Situação |
|-------|----------|
| Coleta de vídeos | ✅ Feita — 2917 vídeos |
| Pré-processamento / limpeza | ✅ Feito — `videos_limpos.csv` gerado |
| Coleta de comentários | ⬜ Pendente (script pronto: `coletor_comentarios.py`) |
| Mineração (agrupamento / engajamento / PT×EN) | ⬜ A fazer — **próximo passo** |
| Relatório (LaTeX) | ⬜ A fazer |
| Apresentação | ⬜ A fazer |

---

## Estrutura do projeto

```
mineracao-de-dados/
├── dados/
│   ├── brutos/          # dado cru da API (NÃO editar na mão)
│   │   ├── videos_masculino.csv
│   │   └── comentarios.csv        (após rodar o coletor de comentários)
│   └── processados/     # dado limpo, usado na mineração
│       └── videos_limpos.csv
├── scripts/
│   ├── coletor_youtube.py     # coleta metadados dos vídeos (acumula)
│   ├── coletor_comentarios.py # coleta comentários dos vídeos
│   └── limpeza.py             # gera a base limpa a partir da bruta
├── notebooks/           # exploração e mineração
├── relatorio/           # relatório em LaTeX
└── README.md
```

**Regra de ouro:** dado bruto nunca é editado na mão. Todo tratamento é feito por
script, gerando uma cópia em `dados/processados/`.

---

## Como rodar

### Pré-requisitos
```
pip3 install --break-system-packages google-api-python-client pandas python-dotenv
```

### Chave da API
Cada integrante usa a **sua própria** chave da YouTube Data API v3 (gratuita, sem
cartão). Guarde-a num arquivo `.env` dentro de `scripts/` (o `.gitignore` já ignora):
```
YT_API_KEY=SUA_CHAVE_AQUI
```

### Ordem de execução (rodar de dentro de `scripts/`)
```
python3 coletor_youtube.py       # 1. coleta/atualiza os vídeos
python3 coletor_comentarios.py   # 2. (opcional) coleta os comentários
python3 limpeza.py               # 3. regenera a base limpa
```
Os caminhos são resolvidos automaticamente — pode rodar de qualquer pasta.

---

## Dicionário de dados (`videos_limpos.csv`)

| Coluna | Descrição |
|--------|-----------|
| `video_id` | ID único do vídeo no YouTube |
| `titulo` / `descricao` | textos do vídeo (emojis e acentos preservados) |
| `canal` | nome do canal |
| `publicado_em` | data/hora de publicação (UTC) |
| `ano` | ano de publicação (derivado) |
| `categoria_id` | categoria do YouTube (ex.: 22 = People & Blogs, 26 = HowTo & Style) |
| `idioma_video` | idioma declarado pelo canal (quando há) |
| `tags` | tags do vídeo, separadas por `\|` |
| `duracao_iso` / `duracao_seg` | duração (ISO 8601 e em segundos) |
| `views` / `likes` / `comentarios` | métricas de engajamento (likes/comentários podem estar ocultos) |
| `termo_busca` / `idioma_termo` | termo e idioma da busca que trouxe o vídeo |

`comentarios.csv`: `comment_id`, `video_id`, `autor`, `texto`, `likes`, `publicado_em`, `respostas`.

---

## Decisões e observações

- **Coleta acumulativa:** o coletor não sobrescreve; lê a base existente e só
  adiciona vídeos inéditos. Dá pra rodar em dias diferentes (variando o `ORDER`:
  `relevance` / `viewCount` / `date`) para crescer a base.
- **Cota da API:** ~10.000 unidades/dia. Cada busca custa 100; cada comentário, 1.
  Se a cota esgotar, os scripts param e retomam no dia seguinte de onde pararam.
- **Limpeza:** normaliza texto (NFC), remove só caracteres invisíveis órfãos e
  **preserva emojis e acentos** (são informação do conteúdo).
- **Privacidade (comentários):** o campo `autor` traz o nome de exibição. Na
  análise, descartar/anonimizar essa coluna e trabalhar só com o texto.

---

## Próximos passos (dividir entre o time)

- [ ] Rodar a coleta de comentários
- [ ] Mineração — temas (agrupamento / topic modeling)
- [ ] Mineração — engajamento por tema/idioma/ano
- [ ] Mineração — comparação PT × EN
- [ ] Levantar 2–4 trabalhos recentes da literatura sobre o tema
- [ ] Escrever o relatório (LaTeX)
- [ ] Montar a apresentação

## Integrantes
Bárbara
Caren
Rafael
