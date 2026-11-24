"""
Gera os áudios da tela de boas-vindas que estiverem faltando.

Para cada perfil do placar.json, cria vozes/<voz>/<nome>.mp3 nas vozes Epaminondas e Clara,
além do geral.mp3. Arquivos que já existem não são refeitos (dá para trocar à mão).
Também gera o resumo falado do tracker (vozes/<voz>/resumo-<nome>.mp3) sempre que os números mudam;
os números de cada resumo ficam em vozes/resumos.json, para o site saber se o áudio está em dia.
Roda no GitHub Actions (.github/workflows/vozes.yml) sempre que o placar.json muda.

Uso: python scripts/gerar_vozes.py <modelo.onnx>
"""
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VOZES = RAIZ / "vozes"
# Filtro do ffmpeg de cada voz (a Clara é a mesma voz com o tom mais agudo).
FILTROS = {
    "epaminondas": "asetrate=16000*0.93,aresample=44100,atempo=1.075,loudnorm=I=-16:TP=-1.5",
    "clara": "asetrate=16000*1.32,aresample=44100,atempo=0.7576,loudnorm=I=-16:TP=-1.5",
}
# Jeito de falar nomes que o leitor pronuncia errado.
PRONUNCIA = {"theus": "Téus"}


def slug(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "perfil"


def gerar(modelo: str, texto: str, destinos: dict) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        txt, wav = Path(tmp) / "t.txt", Path(tmp) / "t.wav"
        txt.write_text(texto, encoding="utf-8")
        subprocess.run([sys.executable, "-m", "piper", "-m", modelo, "-c", modelo + ".json", "-i", str(txt), "-f", str(wav),
                        "--length-scale", "1.12", "--sentence-silence", "0.35"], check=True)
        for voz, destino in destinos.items():
            destino.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav), "-af", FILTROS[voz],
                            "-c:a", "libmp3lame", "-b:a", "96k", str(destino)], check=True)


def resumo(p: dict) -> dict | None:
    """Mesma conta do site: total de ranqueadas salvas, vitórias, derrotas e % de vitória."""
    ms = list(((p.get("valorant") or {}).get("partidas") or {}).values())
    if not ms:
        return None
    n = len(ms)
    v = sum(1 for m in ms if m.get("resultado") == "V")
    d = sum(1 for m in ms if m.get("resultado") == "D")
    return {"n": n, "v": v, "d": d, "wr": int(v * 100 / n + 0.5)}


def texto_resumo(t: dict) -> str:
    return (f"Você tem {t['n']} {'partida' if t['n'] == 1 else 'partidas'}. Ganhou {t['v']}, perdeu {t['d']}, "
            f"e a sua taxa de vitória está em {t['wr']} por cento. Boa sorte hoje!")


def main() -> None:
    modelo = sys.argv[1]
    perfis = json.loads((RAIZ / "placar.json").read_text(encoding="utf-8")).get("perfis", {})
    falas = {"geral": "Seja bem-vindo. O que vai ser para hoje?"}
    for nome in perfis:
        s = slug(nome)
        falas[s] = f"Seja bem-vindo, {PRONUNCIA.get(s, nome)}. O que vai ser para hoje?"
    novos = 0
    for s, texto in falas.items():
        faltando = {v: VOZES / v / f"{s}.mp3" for v in FILTROS if not (VOZES / v / f"{s}.mp3").exists()}
        if faltando:
            gerar(modelo, texto, faltando)
            novos += len(faltando)
            print(f"gerado: {s} -> {', '.join(faltando)}")
    # Resumos do tracker: refaz só quando os números mudaram.
    arq = VOZES / "resumos.json"
    feitos = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    atuais = {}
    for nome, p in perfis.items():
        t = resumo(p)
        if not t:
            continue
        s = slug(nome)
        atuais[s] = t
        faltando = {v: VOZES / v / f"resumo-{s}.mp3" for v in FILTROS}
        if feitos.get(s) != t or not all(f.exists() for f in faltando.values()):
            gerar(modelo, texto_resumo(t), faltando)
            novos += len(faltando)
            print(f"resumo: {s} -> {t}")
    if atuais != feitos:
        arq.write_text(json.dumps(atuais, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{novos} áudio(s) novo(s).")


if __name__ == "__main__":
    main()
