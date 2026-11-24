"""
Servidor do Analytics de Partidas.
Serve a página e grava tudo no placar.json (o "banco de dados").

Uso:
  python server.py          -> http://localhost:8000
  python server.py --rede   -> libera pra outros PCs da mesma rede (Wi-Fi)
"""
import base64
import json
import os
import re
import sys
import threading
import unicodedata
from datetime import date, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "placar.json"
FOTOS = ROOT / "fotos"
JOGOS = ("valorant", "minecraft", "cs", "xadrez")
ELOS = [""] + [f"{n} {i}" for n in ("Ferro", "Bronze", "Prata", "Ouro", "Platina", "Diamante", "Ascendente", "Imortal") for i in (1, 2, 3)] + ["Radiante"]
PIN = re.compile(r"^\d{4}$")
LOCK = threading.Lock()
MAX_BODY = 8 * 1024 * 1024


# ------------------------------------------------------------------ banco
def load() -> dict:
    data = json.loads(DB.read_text(encoding="utf-8")) if DB.exists() else {}
    data.setdefault("perfis", {})
    data.setdefault("jogos", {})
    for p in data["perfis"].values():
        p.setdefault("foto", "")
        p.setdefault("pin", "0000")
        p.setdefault("elo", "")
        p.setdefault("favoritos", [])
        p.setdefault("partidas", {})
        for j in list(JOGOS) + list(data["jogos"]):
            p["partidas"].setdefault(j, {})
    return data


def save(data: dict) -> None:
    tmp = DB.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, DB)


def publico(data: dict) -> dict:
    """Mesmo conteúdo, sem os PINs."""
    return {"jogos": data.get("jogos", {}),
            "perfis": {n: {k: v for k, v in p.items() if k != "pin"} for n, p in data["perfis"].items()}}


# ------------------------------------------------------------------ helpers
def achar(data: dict, nome) -> str:
    alvo = str(nome or "").strip().lower()
    for n in data["perfis"]:
        if n.lower() == alvo:
            return n
    raise ValueError("Perfil não encontrado.")


def autenticar(data: dict, o: dict) -> str:
    nome = achar(data, o.get("nome"))
    if str(o.get("pin")) != str(data["perfis"][nome]["pin"]):
        raise ValueError("PIN errado.")
    return nome


def slug(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "perfil"


def salvar_foto(nome: str, data_url: str) -> str:
    """A foto fica dentro do placar.json (data URL já reduzida pelo site)."""
    m = re.match(r"^data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=]+)$", data_url or "")
    if not m:
        raise ValueError("Foto inválida.")
    if len(data_url) > 200_000:
        raise ValueError("Foto muito grande.")
    return data_url


def elo_valido(elo) -> str:
    elo = str(elo or "")
    if elo not in ELOS:
        raise ValueError("Elo inválido.")
    return elo


def inteiro(v, campo) -> int:
    try:
        n = int(v or 0)
    except (TypeError, ValueError):
        raise ValueError(f"{campo} precisa ser um número inteiro.")
    if abs(n) > 100:
        raise ValueError(f"{campo}: no máximo 100 por vez.")
    return n


# ------------------------------------------------------------------ operações
def apply(data: dict, o: dict) -> dict:
    if not isinstance(o, dict):
        raise ValueError("Operação inválida.")
    op = o.get("op")
    perfis = data["perfis"]

    if op == "login":
        return {"nome": autenticar(data, o)}

    if op == "perfil_criar":
        nome = str(o.get("nome") or "").strip()
        if not nome or len(nome) > 24:
            raise ValueError("Nome precisa ter de 1 a 24 caracteres.")
        if any(n.lower() == nome.lower() for n in perfis):
            raise ValueError("Já existe um perfil com esse nome.")
        pin = str(o.get("pin") or "")
        if not PIN.match(pin):
            raise ValueError("PIN precisa ter 4 números.")
        perfis[nome] = {
            "foto": salvar_foto(nome, o["foto"]) if o.get("foto") else "",
            "pin": pin,
            "elo": elo_valido(o.get("elo")),
            "favoritos": [],
            "partidas": {j: {} for j in list(JOGOS) + list(data["jogos"])},
        }
        return {"nome": nome}

    if op == "valorant_sync":  # partidas ranqueadas vindas do tracker (sem PIN)
        nome = achar(data, o.get("nome"))
        p = perfis[nome]
        v = p.get("valorant")
        if not v or not v.get("conta"):
            raise ValueError("Esse perfil não tem conta do Valorant.")
        if not v.get("migrado"):
            p["partidas"]["valorant"] = {}
            v["migrado"] = True
        v.setdefault("partidas", {})
        if re.match(r"^\d{4}-\d{2}-\d{2}$", str(o.get("desde") or "")) and o["desde"] < v.get("desde", "9"):
            v["desde"] = o["desde"]
        txt = lambda x, n: str(x if x is not None else "")[:n]
        num = lambda x: max(0, min(9999, round(float(x or 0))))
        for m in (o.get("partidas") or [])[:500]:
            if not isinstance(m, dict) or not isinstance(m.get("id"), str) or not m["id"] or len(m["id"]) > 64 or m["id"] in v["partidas"]:
                continue
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(m.get("dia"))) or m["dia"] < v.get("desde", "") or m.get("resultado") not in ("V", "D", "E"):
                continue
            v["partidas"][m["id"]] = {"dia": m["dia"], "hora": txt(m.get("hora"), 5), "resultado": m["resultado"],
                                      "placar": txt(m.get("placar"), 7), "mapa": txt(m.get("mapa"), 20), "agente": txt(m.get("agente"), 20),
                                      "agenteId": txt(m.get("agenteId"), 40), "mapaId": txt(m.get("mapaId"), 40), "k": num(m.get("k")), "d": num(m.get("d")),
                                      "a": num(m.get("a")), "hs": num(m.get("hs")), "acs": num(m.get("acs"))}
        if o.get("elo") and o["elo"] in ELOS:  # elo direto do tracker
            p["elo"] = o["elo"]
        return {"nome": nome}

    if op in ("jogo_criar", "jogo_editar"):  # jogos e cores (precisa estar logado)
        autenticar(data, o)
        jogos = data["jogos"]
        icone = (str(o.get("icone") or "🎮").strip()[:4]) or "🎮"
        cor = o.get("cor")
        if cor and not re.match(r"^#[0-9a-fA-F]{6}$", str(cor)):
            raise ValueError("Cor inválida.")
        if op == "jogo_criar":
            nome_j = str(o.get("jogoNome") or "").strip()
            if not nome_j or len(nome_j) > 20:
                raise ValueError("Nome do jogo: de 1 a 20 caracteres.")
            jid = slug(nome_j)
            if jid in JOGOS or jid in jogos:
                raise ValueError("Esse jogo já existe.")
            jogos[jid] = {"nome": nome_j, "icone": icone, "cor": cor or "#7c5cff"}
            for q in perfis.values():
                q.setdefault("partidas", {}).setdefault(jid, {})
            return {"nome": jid}
        jid = o.get("id")
        if jid not in JOGOS and jid not in jogos:
            raise ValueError("Jogo não encontrado.")
        jogos[jid] = {**jogos.get(jid, {}), "icone": icone, **({"cor": cor} if cor else {})}
        return {"nome": jid}

    nome = autenticar(data, o)
    p = perfis[nome]

    if op == "perfil_editar":
        if o.get("foto"):
            p["foto"] = salvar_foto(nome, o["foto"])
        if "elo" in o:
            p["elo"] = elo_valido(o.get("elo"))
        if "valorant" in o:
            v = o.get("valorant") or {}
            if not v.get("conta"):
                p.pop("valorant", None)
            else:
                if not re.match(r"^[^#]{3,16}#[A-Za-z0-9]{2,5}$", str(v["conta"])):
                    raise ValueError("Use o formato Nome#TAG.")
                if v.get("regiao") not in ("br", "latam", "na", "eu", "ap", "kr"):
                    raise ValueError("Região inválida.")
                antigo = p.get("valorant") or {}
                p["valorant"] = {**antigo, "conta": str(v["conta"]), "regiao": v["regiao"],
                                 "desde": antigo.get("desde") or date.today().replace(month=1, day=1).isoformat()}
        if "boasVindas" in o:
            if o.get("boasVindas"):
                p.pop("boasVindas", None)
            else:
                p["boasVindas"] = False
        if o.get("novoPin"):
            if not PIN.match(str(o["novoPin"])):
                raise ValueError("PIN precisa ter 4 números.")
            p["pin"] = str(o["novoPin"])
        novo = str(o.get("novoNome") or nome).strip()
        if novo != nome:  # troca o nome (a chave) e atualiza os favoritos de todo mundo
            if not novo or len(novo) > 24:
                raise ValueError("Nome precisa ter de 1 a 24 caracteres.")
            if any(k != nome and k.lower() == novo.lower() for k in perfis):
                raise ValueError("Já existe um perfil com esse nome.")
            data["perfis"] = {(novo if k == nome else k): v for k, v in perfis.items()}
            for q in data["perfis"].values():
                q["favoritos"] = [novo if f == nome else f for f in q.get("favoritos", [])]
            return {"nome": novo}

    elif op == "registrar":
        jogo = o.get("jogo")
        if jogo not in JOGOS and jogo not in data["jogos"]:
            raise ValueError("Jogo inválido.")
        g, d = inteiro(o.get("ganhou"), "Ganhou"), inteiro(o.get("perdeu"), "Perdeu")
        if not g and not d:
            raise ValueError("Digite quantas ganhou e/ou perdeu.")
        hoje = date.today().isoformat()
        dias = p["partidas"][jogo]
        dia = dias.get(hoje, {"ganhou": 0, "perdeu": 0})
        dia = {"ganhou": max(0, dia.get("ganhou", 0) + g), "perdeu": max(0, dia.get("perdeu", 0) + d)}
        if dia["ganhou"] or dia["perdeu"]:
            dias[hoje] = dia
        else:
            dias.pop(hoje, None)

    elif op == "aquecimento":  # soma no dia e guarda só os últimos 30 dias
        try:
            sgs = round(float(o.get("segundos") or 0))
        except (TypeError, ValueError):
            sgs = 0
        if sgs < 1 or sgs > 6 * 3600:
            raise ValueError("Tempo de aquecimento inválido (máximo 6 horas).")
        dia = str(o.get("dia") or "")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", dia):
            dia = date.today().isoformat()
        h = p.setdefault("aquecimento", {})
        v = h.get(dia) or {"s": 0, "n": 0}
        h[dia] = {"s": int(v.get("s", 0)) + sgs, "n": int(v.get("n", 0)) + 1}
        limite = (date.today() - timedelta(days=29)).isoformat()
        for k in [k for k in h if k < limite]:
            del h[k]

    elif op == "favorito":
        alvo = achar(data, o.get("alvo"))
        if alvo == nome:
            raise ValueError("Não dá pra favoritar você mesmo.")
        favs = p["favoritos"]
        favs.remove(alvo) if alvo in favs else favs.append(alvo)

    else:
        raise ValueError("Operação desconhecida.")
    return {"nome": nome}


# ------------------------------------------------------------------ HTTP
class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api":
            try:
                with LOCK:
                    return self._json(200, publico(load()))
            except ValueError as e:
                return self._json(500, {"erro": f"placar.json inválido: {e}"})
        if self._bloqueado():
            return self._json(403, {"erro": "Acesso negado."})  # protege os PINs
        return super().do_GET()

    def do_HEAD(self):
        if self._bloqueado():
            return self._json(403, {"erro": "Acesso negado."})
        return super().do_HEAD()

    def _bloqueado(self) -> bool:
        alvo = Path(self.translate_path(self.path)).resolve()
        return alvo == DB or alvo.suffix in (".py", ".tmp", ".pyc")

    def do_POST(self):
        if self.path.split("?")[0] != "/api":
            return self._json(404, {"erro": "Não encontrado."})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("Requisição grande demais.")
            o = json.loads(self.rfile.read(n) or b"{}")
            with LOCK:
                data = load()
                res = apply(data, o)
                if o.get("op") != "login":
                    save(data)
            self._json(200, {**res, **publico(data)})
        except ValueError as e:
            self._json(400, {"erro": str(e)})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    host = "0.0.0.0" if "--rede" in sys.argv else "127.0.0.1"
    port = int(os.environ.get("PORT", 8000))
    srv = ThreadingHTTPServer((host, port), partial(Handler, directory=str(ROOT)))
    print(f"Analytics rodando em http://localhost:{port}  (Ctrl+C pra parar)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
