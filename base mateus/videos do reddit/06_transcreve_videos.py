#!/usr/bin/env python3
"""ETAPA 6 - Baixar o áudio e transcrever os vídeos válidos do YouTube.

Entrada : youtube_videos_validos.csv     (saída da etapa 3; coluna video_id)
Saída   : transcricoes/<video_id>.txt     texto puro de cada vídeo
          06_transcricoes.jsonl           1 linha por vídeo processado, com status, idioma
                                          detectado, duração e texto (permite retomar)
          06_transcricoes.csv             consolidado (video_id + metadados do CSV + texto)
Todos os arquivos ficam na mesma pasta deste script; os áudios vão para audios/ (temporário).

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

Requisitos: ffmpeg (sudo apt install ffmpeg), pip install -U yt-dlp openai-whisper

Uso:
  python 06_transcreve_videos.py --limit 5                 # teste pequeno primeiro
  python 06_transcreve_videos.py                           # tudo
  python 06_transcreve_videos.py --modelo medium --max-duracao 1800
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time

import pandas as pd

PASTA = os.path.dirname(os.path.abspath(__file__))
ENTRADA = os.path.join(PASTA, "youtube_videos_validos.csv")
PASTA_AUDIO = os.path.join(PASTA, "audios")
PASTA_TEXTO = os.path.join(PASTA, "transcricoes")
SAIDA_JSONL = os.path.join(PASTA, "06_transcricoes.jsonl")
SAIDA_CSV = os.path.join(PASTA, "06_transcricoes.csv")

STATUS_ERRO = {"erro_download", "erro_transcricao"}


def carrega_progresso():
    """Último registro de cada video_id já gravado no JSONL."""
    progresso = {}
    if os.path.exists(SAIDA_JSONL):
        with open(SAIDA_JSONL, encoding="utf-8") as f:
            for linha in f:
                if linha.strip():
                    reg = json.loads(linha)
                    progresso[reg["video_id"]] = reg
    return progresso


def salva_registro(reg):
    with open(SAIDA_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")


def baixa_audio(video_id, max_duracao):
    """Baixa o áudio em MP3. Devolve (caminho, None), (None, 'pulado') ou (None, erro)."""
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
        return None, (e.stderr or "").strip().splitlines()[-1:] or ["erro desconhecido"]

    # exit 0 sem arquivo = o --match-filter descartou o vídeo
    if not os.path.exists(caminho):
        return None, "pulado"
    return caminho, None


def exporta_csv(progresso):
    """Junta as transcrições com os metadados do CSV de entrada."""
    df = pd.read_csv(ENTRADA, encoding="utf-8-sig")
    trans = pd.DataFrame(progresso.values())[["video_id", "status", "language", "duration_s", "text"]]
    trans = trans.rename(columns={"text": "transcription"})
    df = df.merge(trans, on="video_id", how="inner")
    df.to_csv(SAIDA_CSV, index=False, encoding="utf-8", quoting=csv.QUOTE_NONNUMERIC)
    return len(df)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="processa só N vídeos pendentes")
    ap.add_argument("--modelo", default="small", help="modelo do Whisper (tiny, base, small, medium...)")
    ap.add_argument("--idioma", default=None, help="força o idioma (ex.: en, pt); padrão: detecção automática")
    ap.add_argument("--sem-traducao", action="store_true", help="não traduz para o inglês")
    ap.add_argument("--max-duracao", type=int, default=3600, help="segundos; 0 = sem limite (padrão 3600)")
    ap.add_argument("--refazer-erros", action="store_true", help="tenta de novo vídeos com status de erro")
    ap.add_argument("--manter-audio", action="store_true", help="não apaga o MP3 após transcrever")
    args = ap.parse_args()

    os.makedirs(PASTA_AUDIO, exist_ok=True)
    os.makedirs(PASTA_TEXTO, exist_ok=True)

    video_ids = pd.read_csv(ENTRADA, encoding="utf-8-sig")["video_id"].astype(str).drop_duplicates().tolist()
    progresso = carrega_progresso()
    pendentes = [
        v for v in video_ids
        if v not in progresso or (args.refazer_erros and progresso[v]["status"] in STATUS_ERRO)
    ]
    if args.limit:
        pendentes = pendentes[:args.limit]
    print(f"{len(video_ids)} vídeos válidos | {len(progresso)} já processados | {len(pendentes)} nesta rodada")
    if not pendentes:
        print(f"Nada a fazer. CSV consolidado: {exporta_csv(progresso)} linhas -> {SAIDA_CSV}")
        return

    # import aqui para o --help e a contagem não precisarem carregar torch
    import torch
    import whisper
    from tqdm import tqdm

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Carregando Whisper '{args.modelo}' em {device}...")
    modelo = whisper.load_model(args.modelo, device=device)
    tarefa = "transcribe" if args.sem_traducao else "translate"

    for video_id in tqdm(pendentes):
        reg = {"video_id": video_id, "status": None, "language": None, "duration_s": None,
               "text": None, "error": None, "model": args.modelo, "task": tarefa,
               "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

        audio, erro = baixa_audio(video_id, args.max_duracao)
        if audio is None:
            reg["status"] = "pulado" if erro == "pulado" else "erro_download"
            reg["error"] = None if erro == "pulado" else " ".join(erro)
            salva_registro(reg)
            progresso[video_id] = reg
            tqdm.write(f"{video_id}: {reg['status']} {reg['error'] or ''}")
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

        salva_registro(reg)
        progresso[video_id] = reg

    contagem = pd.Series([r["status"] for r in progresso.values()]).value_counts()
    print("\nResumo:\n" + contagem.to_string())
    print(f"CSV consolidado: {exporta_csv(progresso)} linhas -> {SAIDA_CSV}")


if __name__ == "__main__":
    sys.exit(main())
