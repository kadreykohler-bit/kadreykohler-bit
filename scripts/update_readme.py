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
        except Exception as e:
            print(
                f"aviso: linguagens de {r['name']}: {e}",
                file=sys.stderr
            )

    if not total:
        return "_Sem dados de linguagens ainda._"

    soma = sum(total.values())
    ranking = total.most_common(6)

    cores = {
        "JavaScript": "#F1E05A",
        "TypeScript": "#3178C6",
        "Python": "#3572A5",
        "HTML": "#E34C26",
        "CSS": "#563D7C",
        "Java": "#B07219",
        "C": "#555555",
        "C++": "#F34B7D",
        "C#": "#178600",
        "PHP": "#4F5D95",
        "Go": "#00ADD8",
        "Shell": "#89E051",
        "Ruby": "#701516",
        "Dart": "#00B4AB",
        "Kotlin": "#A97BFF",
        "SQL": "#E38C00",
    }

    altura = 105 + len(ranking) * 43
    elementos = []

    for i, (nome, qtd) in enumerate(ranking):
        pct = qtd * 100 / soma
        largura = pct * 4.2
        y = 100 + i * 43
        cor = cores.get(nome, "#8B949E")

        nome_svg = (
            nome.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

        elementos.append(f"""
        <text x="28" y="{y}" fill="#E6EDF3"
              font-size="14" font-weight="600">{nome_svg}</text>

        <rect x="165" y="{y - 13}" width="420" height="9"
              rx="5" fill="#30363D"/>

        <rect x="165" y="{y - 13}" width="{largura:.1f}" height="9"
              rx="5" fill="{cor}"/>

        <text x="690" y="{y}" fill="#E6EDF3"
              font-size="13" text-anchor="end">{pct:.1f}%</text>
        """)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg"
        width="720" height="{altura}" viewBox="0 0 720 {altura}">
        <rect width="720" height="{altura}" rx="12" fill="#0D1117"/>

        <text x="28" y="35" fill="#E6EDF3"
              font-size="18" font-weight="bold">
            Linguagens mais utilizadas
        </text>

        <text x="28" y="62" fill="#8B949E" font-size="12">
            Distribuição baseada nos repositórios públicos
        </text>

        {''.join(elementos)}
    </svg>
    """

    os.makedirs("assets", exist_ok=True)

    with open("assets/languages.svg", "w", encoding="utf-8") as arquivo:
        arquivo.write(svg)

    return (
        '<p align="center">'
        '<img src="assets/languages.svg" '
        'alt="Distribuição das linguagens de programação" width="720">'
        '</p>'
    )

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
    linguagens_exibicao = "JavaScript, Python e outras tecnologias"

    descricoes = {
        "Labs-Projetos": (
            "Coleção de projetos práticos envolvendo desenvolvimento "
            "de software, programação e exploração de diferentes tecnologias."
        ),
        "Jornada-Dev": (
            "Repositório dedicado a desafios e exercícios práticos "
            "de desenvolvimento, com foco na evolução contínua em programação."
        ),
        "Portfolio": (
            "Projetos pessoais desenvolvidos para demonstrar conhecimentos "
            "em programação, desenvolvimento de software e Python."
        )
    }

    saida = [
        "| Repositório | Descrição | Linguagens e tecnologias | Atualizado |",
        "|---|---|---|---|"
    ]

    for r in repos:
        link = f"[**{r['name']}**]({r['html_url']})"
        descricao = descricoes.get(
            r["name"],
            r["description"] or "Projetos e estudos de desenvolvimento."
        )

        saida.append(
            f"| {link} | {celula(descricao)} | "
            f"{linguagens_exibicao} | {data_br(r['pushed_at'])} |"
        )

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

            itens.append(
                f"- [{titulo}]({url})" + (f" — {desc}" if desc else "")
            )

        saida += [
            "",
            "<details>",
            f"<summary><b>{r['name']}</b>: {len(pastas)} projetos</summary>",
            "",
            *itens,
            "",
            "</details>"
        ]

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
