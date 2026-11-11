#!/usr/bin/env python3
"""Atualiza o README do perfil com dados REAIS dos repositórios públicos.

Preenche duas áreas do README.md, delimitadas por marcadores:
  <!--LANGUAGES:START--> ... <!--LANGUAGES:END-->
  <!--PROJECTS:START-->  ... <!--PROJECTS:END-->
Todo o resto do README é seu e nunca é alterado.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

USER = os.getenv("GH_USER", "kadreykohler-bit")
TOKEN = os.getenv("GITHUB_TOKEN")
API = "https://api.github.com"
README = "README.md"

IGNORAR_REPOS = {USER}                      # o repositório do próprio perfil
IGNORAR_PASTAS = {"node_modules", ".git", ".github", "dist", "build"}
MIN_PROJETOS_PARA_LISTAR = 2               # só detalha repos com 2+ pastas de projeto
MAX_DESC = 110


def req(url, raw=False):
    headers = {"User-Agent": "profile-readme-updater", "Accept": "application/vnd.github+json"}
    if TOKEN and url.startswith(API):
        headers["Authorization"] = f"Bearer {TOKEN}"
    r = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(r, timeout=30) as resp:
        corpo = resp.read().decode("utf-8", errors="replace")
    return corpo if raw else json.loads(corpo)


def limpar(texto):
    texto = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", texto)   # [texto](link) -> texto
    texto = re.sub(r"[*_`]", "", texto).strip()
    texto = re.sub(r"\s+", " ", texto)
    return texto if len(texto) <= MAX_DESC else texto[: MAX_DESC - 1].rstrip() + "…"


def celula(texto):
    return (texto or "—").replace("|", "/").replace("\n", " ")


def data_br(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}" if iso else "—"


def listar_repos():
    repos, pagina = [], 1
    while True:
        lote = req(f"{API}/users/{USER}/repos?per_page=100&page={pagina}&sort=pushed")
        repos += lote
        if len(lote) < 100:
            break
        pagina += 1
    ativos = [r for r in repos if not r["fork"] and not r["archived"] and r["name"] not in IGNORAR_REPOS]
    return sorted(ativos, key=lambda r: r["pushed_at"] or "", reverse=True)


def bloco_linguagens(repos):
    total = Counter()
    for r in repos:
        try:
            total.update(req(r["languages_url"]))
        except Exception as e:  # um repo com erro não derruba o resto
            print(f"aviso: linguagens de {r['name']}: {e}", file=sys.stderr)
    soma = sum(total.values()) or 1
    linhas = []
    for nome, qtd in total.most_common(6):
        pct = qtd * 100 / soma
        cheio = round(pct / 5)
        linhas.append(f"{nome:<12} {'█' * cheio}{'░' * (20 - cheio)} {pct:5.1f}%")
    if not linhas:
        return "_Sem dados de linguagens ainda._"
    return "```text\n" + "\n".join(linhas) + "\n```"


def pastas_de_projeto(repo):
    """Pastas mais rasas que têm um README.md (ignora subpastas de uma pasta já listada)."""
    branch = repo["default_branch"]
    arvore = req(f"{API}/repos/{USER}/{repo['name']}/git/trees/{branch}?recursive=1")
    readmes = [
        i["path"] for i in arvore.get("tree", [])
        if i["type"] == "blob" and i["path"].lower().endswith("/readme.md")
    ]
    pastas = sorted(p.rsplit("/", 1)[0] for p in readmes if not set(p.split("/")) & IGNORAR_PASTAS)
    topo = []
    for p in pastas:
        if not any(p.startswith(t + "/") for t in topo):
            topo.append(p)
    return branch, topo


def titulo_e_descricao(repo_nome, branch, pasta):
    url = (f"https://raw.githubusercontent.com/{USER}/{repo_nome}/{branch}/"
           f"{urllib.parse.quote(pasta)}/README.md")
    try:
        texto = req(url, raw=True)
    except Exception:
        return None, None
    titulo = desc = None
    for linha in texto.splitlines():
        l = linha.strip()
        if not l or l.startswith(("<", "!", "[![", "```", "---", "|", ">")):
            continue
        if l.startswith("#"):
            titulo = titulo or limpar(l.lstrip("#"))
            continue
        desc = limpar(l)
        break
    return titulo, desc


def nome_da_pasta(pasta):
    ultimo = pasta.rsplit("/", 1)[-1]
    ultimo = re.sub(r"^\d+[-_ ]*", "", ultimo)
    return ultimo.replace("-", " ").replace("_", " ").strip() or pasta


def bloco_projetos(repos):
    saida = ["| Repositório | Descrição | Linguagem | Atualizado |", "|---|---|---|---|"]
    for r in repos:
        link = f"[**{r['name']}**]({r['html_url']})"
        saida.append(f"| {link} | {celula(r['description'])} | {celula(r['language'])} | {data_br(r['pushed_at'])} |")

    for r in repos:
        try:
            branch, pastas = pastas_de_projeto(r)
        except Exception as e:
            print(f"aviso: árvore de {r['name']}: {e}", file=sys.stderr)
            continue
        if len(pastas) < MIN_PROJETOS_PARA_LISTAR:
            continue
        itens = []
        for pasta in pastas:
            titulo, desc = titulo_e_descricao(r["name"], branch, pasta)
            titulo = titulo or nome_da_pasta(pasta)
            url = f"{r['html_url']}/tree/{branch}/{urllib.parse.quote(pasta)}"
            itens.append(f"- [{titulo}]({url})" + (f" — {desc}" if desc else ""))
        saida += ["", f"<details>", f"<summary><b>{r['name']}</b>: {len(pastas)} projetos</summary>", "", *itens, "", "</details>"]
    return "\n".join(saida)


def trocar(texto, nome, conteudo):
    padrao = re.compile(rf"(<!--{nome}:START-->)(.*?)(<!--{nome}:END-->)", re.S)
    if not padrao.search(texto):
        raise SystemExit(f"Marcador {nome} não encontrado no {README}")
    return padrao.sub(lambda m: f"{m.group(1)}\n{conteudo}\n{m.group(3)}", texto)


def main():
    repos = listar_repos()
    print(f"{len(repos)} repositórios públicos encontrados")
    with open(README, encoding="utf-8") as f:
        texto = f.read()
    texto = trocar(texto, "LANGUAGES", bloco_linguagens(repos))
    texto = trocar(texto, "PROJECTS", bloco_projetos(repos))
    with open(README, "w", encoding="utf-8") as f:
        f.write(texto)
    print("README atualizado")


if __name__ == "__main__":
    main()
