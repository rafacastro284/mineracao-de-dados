#!/usr/bin/env python3
"""ETAPA 6 - Baixar o áudio e transcrever os vídeos válidos do YouTube.

Entrada : youtube_videos_validos.csv     (saída da etapa 3; coluna video_id)
Saída   : transcricoes/<video_id>.txt     texto puro de cada vídeo
          06_transcricoes.jsonl           1 linha por vídeo processado, com status, idioma
                                          detectado, duração e texto (permite retomar)
          06_transcricoes.csv             consolidado (video_id + metadados do CSV + texto)
Pastas (em videosDoReddit/): entrada/ -> cache/ (JSONL) e resultados/ (CSV); áudios em audios/ (temporário).

Status possíveis (06_transcricoes.jsonl):
  ok               áudio baixado e transcrito
  pulado           filtro do yt-dlp descartou o vídeo (live ou mais longo que --max-duracao)
  erro_download    yt-dlp falhou (removido depois da validação, privado, restrição de idade...)
  erro_transcricao Whisper falhou (mensagem no campo 'error')

Adaptações em relação ao notebook da Fase 17:
- Não refaz a checagem de disponibilidade (oEmbed): a etapa 3 já validou pela API.
- Idioma detectado automaticamente pelo Whisper (os vídeos do Reddit são, na maioria, em
  inglês), e o idioma original fica salvo no JSONL. Use --idioma para forçar um.
- O texto sai traduzido para o inglês (task="translate" do Whisper), para a base ficar num
  idioma só. --sem-traducao mantém o texto no idioma original.
- yt-dlp roda com --js-runtimes node (sem runtime JS o YouTube devolve "not available").
- Lives e vídeos longos são descartados no próprio yt-dlp (--match-filter), sem baixar nada.
- O progresso fica no JSONL; vídeos já processados (qualquer status) não são refeitos.
  Use --refazer-erros para tentar de novo os que deram erro.
- O MP3 é apagado depois da transcrição (zipar MP3 não economiza espaço). --manter-audio mantém.

Proteções contra o que deu errado na primeira rodada completa:
- Só uma execução por vez (trava em 06_transcricoes.lock); a segunda sai com uma mensagem.
- Um registro 'ok' nunca é substituído por um erro posterior do mesmo vídeo.
- --pausa segundos (mais uma variação aleatória) entre vídeos, para não provocar o bloqueio.
- Bloqueio do YouTube ("not a bot", HTTP 429...): o vídeo NÃO é marcado como erro. O script
  espera (--pausa-bloqueio, dobrando até 2 h) e tenta o mesmo vídeo de novo; depois de
  --max-bloqueios esperas seguidas, grava o CSV e encerra. Antes de esperar, testa um vídeo
  que já deu certo: se ele abre, o bloqueio é só daquele vídeo, que vira erro_download.
- low_content (CSV): status ok com menos de 50 caracteres (vídeos sem fala, alucinações).
- O Whisper detecta o idioma só pelos primeiros 30 s; em vídeos que começam com música ou
  silêncio ele chuta idiomas como nn, cy, jw, la. Com --idioma o registro guarda
  language_forced=True. Com --idioma en a tarefa vira "transcribe" (traduzir inglês para
  inglês só piora o texto).

Requisitos: ffmpeg (sudo apt install ffmpeg), pip install -U yt-dlp openai-whisper

Uso:
  python 06_transcreve_videos.py --limit 5                 # teste pequeno primeiro
  python 06_transcreve_videos.py                           # tudo
  python 06_transcreve_videos.py --modelo medium --max-duracao 1800
  python 06_transcreve_videos.py --refazer-erros           # tenta de novo os que falharam
  python 06_transcreve_videos.py --so-exportar             # só refaz o CSV a partir do JSONL
  python 06_transcreve_videos.py --refazer-erros --parte 2/3   # pessoa 2 de 3 (em paralelo)
  python 06_transcreve_videos.py --videos ID1,ID2 --idioma en --modelo medium
                                    # refaz vídeos já transcritos (ex.: idioma detectado errado);
                                    # o registro novo substitui o antigo no JSONL
"""
import argparse
import csv
import glob
import json
import os
import random
import re
import subprocess
import sys
import time

import pandas as pd

try:
    import fcntl
except ImportError:  # Windows: sem trava entre execuções
    fcntl = None

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # scripts/ -> videosDoReddit/
PASTA_CACHE = os.path.join(PASTA, "cache")
ENTRADA = os.path.join(PASTA, "entrada", "youtube_videos_validos.csv")
PASTA_AUDIO = os.path.join(PASTA, "audios")
PASTA_TEXTO = os.path.join(PASTA, "transcricoes")
SAIDA_JSONL = os.path.join(PASTA_CACHE, "06_transcricoes.jsonl")
SAIDA_CSV = os.path.join(PASTA, "resultados", "06_transcricoes.csv")
TRAVA = os.path.join(PASTA_CACHE, "06_transcricoes.lock")

STATUS_ERRO = {"erro_download", "erro_transcricao"}
BLOQUEADO = "bloqueado"
RE_BLOQUEIO = re.compile(r"not a bot|Please sign in|HTTP Error 429|rate.?limit", re.IGNORECASE)
MIN_CARACTERES = 50
ESPERA_MAXIMA = 7200


def carrega_progresso():
    """Último registro de cada video_id nos JSONL (principal e partes); um 'ok' não é substituído por erro."""
    progresso = {}
    for caminho in sorted(glob.glob(os.path.join(PASTA_CACHE, "06_transcricoes*.jsonl"))):
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                if linha.strip():
                    reg = json.loads(linha)
                    anterior = progresso.get(reg["video_id"])
                    if anterior is None or anterior["status"] != "ok" or reg["status"] == "ok":
                        progresso[reg["video_id"]] = reg
    return progresso


def salva_registro(reg, caminho):
    with open(caminho, "a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")


def baixa_audio(video_id, max_duracao):
    """Baixa o áudio em MP3. Devolve (caminho, None), (None, 'pulado'), (None, BLOQUEADO) ou (None, erro)."""
    caminho = os.path.join(PASTA_AUDIO, f"{video_id}.mp3")
    if os.path.exists(caminho):
        return caminho, None

    filtro = "!is_live"
    if max_duracao:
        filtro += f" & duration <= {max_duracao}"

    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        subprocess.run(
            ["yt-dlp", "-f", "bestaudio", "--extract-audio", "--audio-format", "mp3",
             "--js-runtimes", "node", "--match-filter", filtro, "--no-playlist",
             "-o", os.path.join(PASTA_AUDIO, "%(id)s.%(ext)s"), url],
            check=True, text=True, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        if RE_BLOQUEIO.search(stderr):
            return None, BLOQUEADO
        return None, stderr.splitlines()[-1] if stderr else "erro desconhecido"

    # exit 0 sem arquivo = o --match-filter descartou o vídeo
    if not os.path.exists(caminho):
        return None, "pulado"
    return caminho, None


def youtube_liberado(video_controle):
    """Testa um vídeo que já deu certo: se ele abre, o 'Please sign in' era só do vídeo atual."""
    r = subprocess.run(
        ["yt-dlp", "--simulate", "--js-runtimes", "node", "--no-playlist",
         f"https://www.youtube.com/watch?v={video_controle}"],
        text=True, capture_output=True,
    )
    return r.returncode == 0


def exporta_csv(progresso):
    """Junta as transcrições com os metadados do CSV de entrada."""
    df = pd.read_csv(ENTRADA, encoding="utf-8-sig")
    trans = pd.DataFrame(progresso.values())[["video_id", "status", "language", "duration_s", "text"]]
    trans["low_content"] = (trans["status"] == "ok") & (trans["text"].fillna("").str.len() < MIN_CARACTERES)
    trans = trans.rename(columns={"text": "transcription"})
    df = df.merge(trans, on="video_id", how="inner")
    df.to_csv(SAIDA_CSV, index=False, encoding="utf-8", quoting=csv.QUOTE_NONNUMERIC)
    return len(df)


def finaliza(progresso, parte):
    """Grava o CSV consolidado; numa --parte não grava, para não dar conflito no Git."""
    if parte:
        print(f"Parte {parte[0]}/{parte[1]} gravada em 06_transcricoes_parte{parte[0]}.jsonl "
              "(o CSV é gerado depois com --so-exportar, juntando todas as partes)")
    else:
        print(f"CSV consolidado: {exporta_csv(progresso)} linhas -> {SAIDA_CSV}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="processa só N vídeos pendentes")
    ap.add_argument("--modelo", default="small", help="modelo do Whisper (tiny, base, small, medium...)")
    ap.add_argument("--idioma", default=None, help="força o idioma (ex.: en, pt); padrão: detecção automática")
    ap.add_argument("--sem-traducao", action="store_true", help="não traduz para o inglês")
    ap.add_argument("--max-duracao", type=int, default=3600, help="segundos; 0 = sem limite (padrão 3600)")
    ap.add_argument("--refazer-erros", action="store_true", help="tenta de novo vídeos com status de erro")
    ap.add_argument("--manter-audio", action="store_true", help="não apaga o MP3 após transcrever")
    ap.add_argument("--pausa", type=float, default=20, help="segundos entre vídeos (padrão 20, mais até 50%% aleatório)")
    ap.add_argument("--pausa-bloqueio", type=int, default=1800, help="primeira espera ao ser bloqueado, em segundos (padrão 1800)")
    ap.add_argument("--max-bloqueios", type=int, default=6, help="esperas seguidas antes de encerrar (padrão 6)")
    ap.add_argument("--videos", help="IDs separados por vírgula: processa só esses, mesmo os já transcritos")
    ap.add_argument("--so-exportar", action="store_true", help="só refaz o CSV a partir do JSONL")
    ap.add_argument("--parte", help="K/N: processa só a parte K de N (para dividir entre pessoas); grava em 06_transcricoes_parteK.jsonl")
    args = ap.parse_args()

    parte = None
    if args.parte:
        k, n = (int(x) for x in args.parte.split("/"))
        if not 1 <= k <= n:
            ap.error("--parte deve ser K/N com 1 <= K <= N, ex.: --parte 2/3")
        parte = (k, n)
    saida_jsonl = os.path.join(PASTA_CACHE, f"06_transcricoes_parte{parte[0]}.jsonl") if parte else SAIDA_JSONL

    trava = open(TRAVA, "w")
    try:
        if fcntl:
            fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Já existe outra execução deste script rodando. Saindo.")
        return 1

    os.makedirs(PASTA_AUDIO, exist_ok=True)
    os.makedirs(PASTA_TEXTO, exist_ok=True)

    video_ids = pd.read_csv(ENTRADA, encoding="utf-8-sig")["video_id"].astype(str).drop_duplicates().tolist()
    progresso = carrega_progresso()
    if args.so_exportar:
        print(f"CSV consolidado: {exporta_csv(progresso)} linhas -> {SAIDA_CSV}")
        return 0
    pendentes = [
        v for v in video_ids
        if v not in progresso or (args.refazer_erros and progresso[v]["status"] in STATUS_ERRO)
    ]
    if args.videos:
        pedidos = [v.strip() for v in args.videos.split(",") if v.strip()]
        fora = [v for v in pedidos if v not in video_ids]
        if fora:
            ap.error(f"IDs fora de {os.path.basename(ENTRADA)}: {', '.join(fora)}")
        pendentes = pedidos
    if parte:
        # divide pela posição no CSV de entrada: a divisão não muda conforme o progresso avança
        minha = {v for i, v in enumerate(video_ids) if i % parte[1] == parte[0] - 1}
        pendentes = [v for v in pendentes if v in minha]
    if args.limit:
        pendentes = pendentes[:args.limit]
    print(f"{len(video_ids)} vídeos válidos | {len(progresso)} já processados | {len(pendentes)} nesta rodada")
    if not pendentes:
        print("Nada a fazer.")
        finaliza(progresso, parte)
        return

    # import aqui para o --help e a contagem não precisarem carregar torch
    import torch
    import whisper
    from tqdm import tqdm

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Carregando Whisper '{args.modelo}' em {device}...")
    modelo = whisper.load_model(args.modelo, device=device)
    tarefa = "transcribe" if args.sem_traducao or args.idioma == "en" else "translate"

    video_controle = next((v for v, r in progresso.items() if r["status"] == "ok"), "dQw4w9WgXcQ")
    bloqueios = 0
    for video_id in tqdm(pendentes):
        while True:
            audio, erro = baixa_audio(video_id, args.max_duracao)
            if erro == BLOQUEADO and youtube_liberado(video_controle):
                erro = "vídeo pede login (restrição do próprio vídeo, não bloqueio geral)"
            if erro != BLOQUEADO:
                bloqueios = 0
                break
            bloqueios += 1
            if bloqueios > args.max_bloqueios:
                print(f"\nYouTube continua bloqueando após {args.max_bloqueios} esperas. Encerrando; rode de novo mais tarde.")
                finaliza(progresso, parte)
                return 1
            espera = min(args.pausa_bloqueio * 2 ** (bloqueios - 1), ESPERA_MAXIMA)
            tqdm.write(f"{time.strftime('%d/%m %H:%M')} bloqueio do YouTube em {video_id}: esperando {espera // 60} min ({bloqueios}/{args.max_bloqueios})")
            time.sleep(espera)

        reg = {"video_id": video_id, "status": None, "language": None, "duration_s": None,
               "text": None, "error": None, "model": args.modelo, "task": tarefa,
               "language_forced": bool(args.idioma),
               "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

        if audio is None:
            reg["status"] = "pulado" if erro == "pulado" else "erro_download"
            reg["error"] = None if erro == "pulado" else erro
            salva_registro(reg, saida_jsonl)
            progresso[video_id] = reg
            tqdm.write(f"{video_id}: {reg['status']} {reg['error'] or ''}")
            time.sleep(args.pausa * random.uniform(1, 1.5))
            continue

        try:
            result = modelo.transcribe(audio, task=tarefa, language=args.idioma, fp16=(device == "cuda"))
            texto = result["text"].strip()
            with open(os.path.join(PASTA_TEXTO, f"{video_id}.txt"), "w", encoding="utf-8") as f:
                f.write(texto)
            segmentos = result.get("segments") or []
            reg.update(status="ok", language=result.get("language"), text=texto,
                       duration_s=round(segmentos[-1]["end"], 1) if segmentos else None)
            if not args.manter_audio:
                os.remove(audio)
        except Exception as e:  # noqa: BLE001 - registra e segue para o próximo
            reg.update(status="erro_transcricao", error=str(e))
            tqdm.write(f"{video_id}: erro_transcricao {e}")

        salva_registro(reg, saida_jsonl)
        progresso[video_id] = reg
        time.sleep(args.pausa * random.uniform(1, 1.5))

    contagem = pd.Series([r["status"] for r in progresso.values()]).value_counts()
    print("\nResumo:\n" + contagem.to_string())
    finaliza(progresso, parte)


if __name__ == "__main__":
    sys.exit(main())
