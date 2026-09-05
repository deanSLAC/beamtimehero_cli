"""Static HTML index of the scientific core — the human view of ``science/``.

Sibling to :mod:`beamtimehero_cli.docgen` (which renders the agent-facing tool
catalog). This one renders the *science* surface for the people who work on it:

    python -m beamtimehero_cli.docgen_science          # docs/science_index.html
    python -m beamtimehero_cli.docgen_science -o x.html

Every function under ``science/`` appears with its signature, the first line of
its docstring, and — the part that is hard to get by reading — **which tools
reach it**. That reverse index is computed from a call graph over
``tool_catalog``, ``spec_data`` and ``science`` itself, so an indirect route
(tool -> handler -> spec_data -> science) is followed as well as a direct call.

Module ``CITATIONS`` dicts are collected into a bibliography, and entries whose
value is ``None`` are listed as attribution gaps — a standing to-do list for
contributors.

Data comes from the source tree itself, so the page cannot drift: a new science
function appears here by existing.
"""
from __future__ import annotations

import argparse
import ast
import html
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent
PKG_NAME = "beamtimehero_cli"

# Packages walked when building the call graph. science/ is the subject;
# the others are included so indirect routes from a tool are followed.
GRAPH_ROOTS = ("science", "spec_data", "tool_catalog", "experiment_planning")

# Display order and blurb for the science directories.
DIR_ORDER = ["tables", "reduce", "statistics", "xas", "exafs", "xrs",
             "fitting", "plots"]
DIR_NOTES = {
    "tables": "Tabulated physics. Data, not algorithms — the values most often "
              "corrected or extended, readable without touching any code.",
    "reduce": "Detector counts to one clean spectrum. Technique-agnostic: "
              "nothing here assumes an absorption edge.",
    "statistics": "Statistics over a stack of repeated scans — convergence, "
                  "repetition efficiency, spot heterogeneity. Judges a set of "
                  "reps rather than producing one spectrum.",
    "xas": "XANES / HERFD. Pipeline order: normalize, e0, fits, descriptors, "
           "interpret — with compare for cross-spectrum work.",
    "exafs": "EXAFS k-space: energy/wavenumber conversion, background removal, "
             "Fourier transform into R space.",
    "xrs": "X-ray Raman on the energy-loss axis. Kept apart from xas/ because "
           "the XAS defaults are actively wrong here.",
    "fitting": "Generic fitting and similarity helpers — not spectroscopy. "
               "Only scan-to-scan similarity so far; the knife-edge and "
               "emission-peak fits have not moved here.",
    "plots": "Figures over arrays and descriptor dicts. A figure that takes a "
             "file name belongs in spec_data/ instead.",
}


# ---------------------------------------------------------------------------
# Source scanning
# ---------------------------------------------------------------------------

def _iter_modules(root: str):
    """Yield ``(dotted_name, path, ast)`` for every module under ``root``."""
    for p in sorted((PKG / root).rglob("*.py")):
        rel = p.relative_to(PKG).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        dotted = ".".join([PKG_NAME] + parts)
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError:  # pragma: no cover — never seen in-tree
            continue
        yield dotted, p, tree


def _signature(fn: ast.FunctionDef) -> str:
    """Render a def's parameter list, defaults elided to keep it scannable."""
    a = fn.args
    names: list[str] = []
    pos = list(a.posonlyargs) + list(a.args)
    n_def = len(a.defaults)
    split = len(pos) - n_def
    for i, arg in enumerate(pos):
        names.append(arg.arg if i < split else f"{arg.arg}=...")
    if a.vararg:
        names.append("*" + a.vararg.arg)
    elif a.kwonlyargs:
        names.append("*")
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        names.append(arg.arg if d is None else f"{arg.arg}=...")
    if a.kwarg:
        names.append("**" + a.kwarg.arg)
    return f"({', '.join(names)})"


def _first_line(node) -> str:
    doc = ast.get_docstring(node) or ""
    for line in doc.strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def _alias_map(body) -> dict[str, str]:
    """name -> dotted module, for imports appearing in ``body``."""
    out: dict[str, str] = {}
    for n in body:
        if isinstance(n, ast.Import):
            for al in n.names:
                out[al.asname or al.name.split(".")[0]] = al.name
        elif isinstance(n, ast.ImportFrom):
            mod = n.module or ""
            if not mod.startswith(PKG_NAME):
                continue
            for al in n.names:
                # `from pkg.a import b as c` — b may be a module or a function;
                # record both readings and let resolution prefer the module.
                out[al.asname or al.name] = f"{mod}.{al.name}"
    return out


def _defined_names(tree: ast.Module) -> set[str]:
    out = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
    return out


def scan() -> dict:
    """Collect modules, functions, citations, and the call graph."""
    modules: dict[str, dict] = {}
    trees: dict[str, ast.Module] = {}

    for root in GRAPH_ROOTS:
        for dotted, path, tree in _iter_modules(root):
            trees[dotted] = tree
            fns = {}
            for n in tree.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fns[n.name] = {
                        "name": n.name,
                        "signature": _signature(n),
                        "doc": _first_line(n),
                        "private": n.name.startswith("_"),
                        "lineno": n.lineno,
                    }
            modules[dotted] = {
                "dotted": dotted,
                "rel": str(path.relative_to(PKG)),
                "doc": _first_line(tree),
                "functions": fns,
                "constants": [
                    t.id for n in tree.body if isinstance(n, ast.Assign)
                    for t in n.targets
                    if isinstance(t, ast.Name) and t.id.isupper()
                ],
                "citations": _citations(dotted),
                "is_science": dotted.startswith(f"{PKG_NAME}.science"),
            }

    graph = _call_graph(modules, trees)
    graph = _resolve_reexports(graph, modules, trees)
    return {"modules": modules, "graph": graph, "tools": _tool_entrypoints()}


def _reexport_origins(trees: dict) -> dict[tuple[str, str], str]:
    """(module, name) -> module it was from-imported from.

    ``science.xas.descriptors`` imports ``find_e0`` from ``science.xas.e0``, so
    a handler calling ``interp_desc.find_e0`` resolves, correctly but
    unhelpfully, to the descriptors namespace. This lets the graph point at the
    module that actually defines the function, which is where a contributor
    would go to change it.
    """
    out: dict[tuple[str, str], str] = {}
    for dotted, tree in trees.items():
        for n in tree.body:
            if not isinstance(n, ast.ImportFrom):
                continue
            mod = n.module or ""
            if not mod.startswith(PKG_NAME):
                continue
            for al in n.names:
                out[(dotted, al.asname or al.name)] = mod
    return out


def _resolve_reexports(graph, modules, trees):
    """Redirect edges that land on a re-exporting module to the definer."""
    origins = _reexport_origins(trees)

    def fix(node, _depth=0):
        mod, fn = node
        if _depth > 4 or mod not in modules:
            return node
        if fn in modules[mod]["functions"]:
            return node
        src = origins.get((mod, fn))
        if src and src in modules:
            return fix((src, fn), _depth + 1)
        return node

    return {fix(k): {fix(v) for v in vs} for k, vs in graph.items()}


def _citations(dotted: str) -> dict:
    """Import the module and read its CITATIONS dict (source of truth)."""
    try:
        import importlib
        mod = importlib.import_module(dotted)
    except Exception:  # pragma: no cover — a broken module has no citations
        return {}
    c = getattr(mod, "CITATIONS", None)
    return dict(c) if isinstance(c, dict) else {}


def _call_graph(modules: dict, trees: dict) -> dict[tuple[str, str], set]:
    """(module, func) -> set of callees, resolved through import aliases."""
    edges: dict[tuple[str, str], set] = {}

    for dotted, tree in trees.items():
        mod_aliases = _alias_map(tree.body)
        local_defs = _defined_names(tree)

        for n in tree.body:
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            aliases = dict(mod_aliases)
            aliases.update(_alias_map([x for x in ast.walk(n)
                                       if isinstance(x, (ast.Import, ast.ImportFrom))]))
            key = (dotted, n.name)
            edges.setdefault(key, set())

            # Bare references count too: interpret.py picks its oxidation
            # branch out of a {family: function} table, so those functions are
            # never syntactically Called even though they are very much used.
            called_at = {id(c.func) for c in ast.walk(n) if isinstance(c, ast.Call)}
            for ref in ast.walk(n):
                if id(ref) in called_at:
                    continue
                if isinstance(ref, ast.Name) and isinstance(ref.ctx, ast.Load):
                    if ref.id in local_defs:
                        edges[key].add((dotted, ref.id))
                    else:
                        tgt = aliases.get(ref.id)
                        if tgt:
                            owner, _, fname = tgt.rpartition(".")
                            if owner in modules and fname in modules[owner]["functions"]:
                                edges[key].add((owner, fname))
                elif (isinstance(ref, ast.Attribute)
                      and isinstance(ref.value, ast.Name)
                      and isinstance(ref.ctx, ast.Load)):
                    tgt = aliases.get(ref.value.id)
                    if tgt and tgt in modules and ref.attr in modules[tgt]["functions"]:
                        edges[key].add((tgt, ref.attr))

            for call in ast.walk(n):
                if not isinstance(call, ast.Call):
                    continue
                f = call.func
                if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                    target = aliases.get(f.value.id)
                    if target and target in modules:
                        edges[key].add((target, f.attr))
                elif isinstance(f, ast.Name):
                    target = aliases.get(f.id)
                    if target:
                        owner, _, fname = target.rpartition(".")
                        if owner in modules:
                            edges[key].add((owner, fname))
                    elif f.id in local_defs:
                        edges[key].add((dotted, f.id))
    return edges


def _tool_entrypoints() -> list[dict]:
    """Every catalog leaf with the (module, func) its handler lives at."""
    from beamtimehero_cli.tool_catalog.tools_core import DISPATCH
    out = []
    for path, handler in sorted(DISPATCH.items()):
        out.append({
            "tree": path[:-1],
            "name": path[-1],
            "cli": " ".join(list(path[:-1]) + [path[-1].replace("_", "-")]),
            "handler": (getattr(handler, "__module__", ""),
                        getattr(handler, "__name__", "")),
        })
    return out


def reverse_index(data: dict) -> dict[tuple[str, str], set[str]]:
    """(science module, func) -> set of CLI tool paths that reach it."""
    graph, out = data["graph"], {}
    for tool in data["tools"]:
        start = tool["handler"]
        seen, stack = set(), [start]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for callee in graph.get(cur, ()):
                if callee not in seen:
                    stack.append(callee)
        for mod, fn in seen:
            if mod.startswith(f"{PKG_NAME}.science"):
                out.setdefault((mod, fn), set()).add(tool["cli"])
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _esc(s) -> str:
    return html.escape(str(s or ""))


def _short(dotted: str) -> str:
    return dotted.replace(f"{PKG_NAME}.science.", "")


_CSS = """
:root {
  --paper:#f6f2ea; --panel:#fdfbf6; --ink:#221d14; --dim:#6f6656;
  --rule:#d9d1bf; --rule-strong:#a89c82; --accent:#9a3412; --code-bg:#ede7d9;
  --shadow:0 1px 3px rgba(60,48,20,.08); --gap:#8f6a1d;
  --c-tables:#8a5a1f; --c-reduce:#58622a; --c-xas:#1d5a96; --c-exafs:#316648;
  --c-xrs:#7b3d8f; --c-fitting:#5c5c66; --c-plots:#9c2b60;
}
:root[data-theme="dark"] {
  --paper:#17130c; --panel:#201a11; --ink:#e9e1cf; --dim:#a2937a;
  --rule:#3a3323; --rule-strong:#5c5138; --accent:#e8863c; --code-bg:#2c2517;
  --shadow:0 1px 3px rgba(0,0,0,.5); --gap:#d8bf62;
  --c-tables:#d9a659; --c-reduce:#b3c163; --c-xas:#6aabe8; --c-exafs:#7cc39a;
  --c-xrs:#c98add; --c-fitting:#b0b0bd; --c-plots:#e577ab;
}
*{box-sizing:border-box} html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);
  font:16px/1.55 Charter,"Iowan Old Style",Cambria,Georgia,serif;
  background-image:radial-gradient(rgba(120,100,60,.06) 1px,transparent 1px);
  background-size:26px 26px}
code,.mono,.sig{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:.86em}
code{background:var(--code-bg);padding:.1em .35em;border-radius:3px}
a{color:var(--accent)}
.wrap{max-width:960px;margin:0 auto;padding:0 24px 96px}
header{padding:56px 0 0}
.eyebrow{letter-spacing:.22em;text-transform:uppercase;font-size:.72rem;color:var(--dim);
  font-family:ui-monospace,Menlo,monospace}
h1{font-size:2.6rem;margin:.2em 0 .1em;font-weight:600;letter-spacing:-.01em}
h1 .thin{color:var(--accent);font-style:italic;font-weight:400}
.lede{max-width:64ch;color:var(--dim);margin-top:.4em}
.statstrip{display:flex;flex-wrap:wrap;gap:0 36px;margin:28px 0 0;
  border-top:3px double var(--rule-strong);border-bottom:1px solid var(--rule);padding:12px 0}
.stat b{display:block;font-size:1.5rem;font-weight:600}
.stat span{font-size:.68rem;letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
#themetoggle{margin-left:auto;align-self:center;cursor:pointer;background:none;
  border:1px solid var(--rule-strong);color:var(--ink);border-radius:999px;
  padding:.35em .9em;font:inherit;font-size:.8rem}
h2{margin:60px 0 6px;font-size:1.5rem;display:flex;align-items:baseline;gap:.6em}
h2 .no{color:var(--accent);font-family:ui-monospace,Menlo,monospace;font-size:.8em;font-weight:400}
.sectionnote{color:var(--dim);margin:0 0 20px;max-width:70ch}
.therule{border:3px double var(--rule-strong);border-radius:6px;background:var(--panel);
  padding:20px 26px;margin:20px 0;box-shadow:var(--shadow)}
.therule blockquote{margin:0;font-size:1.12rem;line-height:1.5;max-width:58ch}
.therule blockquote b{color:var(--accent)}
.dir{background:var(--panel);border:1px solid var(--rule);border-left:5px solid var(--c,var(--rule-strong));
  border-radius:6px;margin:12px 0;box-shadow:var(--shadow)}
.dir>summary{display:flex;align-items:center;gap:12px;padding:11px 16px;cursor:pointer;list-style:none}
.dir>summary::before{content:"\\25B8";color:var(--dim);font-size:.8em;transition:transform .15s}
.dir[open]>summary::before{transform:rotate(90deg)}
.dir .dname{font-weight:600;font-family:ui-monospace,Menlo,monospace;font-size:.9rem}
.dir .count{margin-left:auto;font-family:ui-monospace,Menlo,monospace;font-size:.78rem;
  color:var(--dim);border:1px solid var(--rule);border-radius:999px;padding:.05em .6em}
.dir .note{margin:0 16px 10px 42px;color:var(--dim);font-size:.9rem;max-width:70ch}
.modblock{margin:0 16px 14px 42px}
.modhead{display:flex;align-items:baseline;gap:10px;border-bottom:1px solid var(--rule);
  padding-bottom:3px;margin:14px 0 8px}
.modhead .mpath{font-family:ui-monospace,Menlo,monospace;font-size:.84rem;font-weight:600}
.modhead .mdoc{color:var(--dim);font-size:.86rem}
.fn{padding:5px 0 5px 0;border-bottom:1px dotted var(--rule)}
.fn:last-child{border-bottom:0}
.fn .sig{font-size:.82rem}
.fn .fname{font-weight:600}
.fn .fdoc{color:var(--dim);font-size:.88rem;margin:.15em 0 0;max-width:78ch}
.fn.priv .fname{font-weight:400;color:var(--dim)}
.fn.const .users b{color:var(--accent)}
.users{margin:.3em 0 0;font-size:.76rem;color:var(--dim);
  font-family:ui-monospace,Menlo,monospace}
.users b{color:var(--ink);font-weight:600}
.users .none{font-style:italic;font-family:Charter,Georgia,serif}
.chip{font-family:ui-monospace,Menlo,monospace;font-size:.7rem;padding:.1em .5em;
  border-radius:999px;white-space:nowrap;color:var(--c,var(--dim));
  background:color-mix(in srgb,var(--c,var(--dim)) 12%,transparent);
  border:1px solid color-mix(in srgb,var(--c,var(--dim)) 40%,transparent)}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:.88rem}
th,td{text-align:left;padding:.45em .7em;border-bottom:1px solid var(--rule);vertical-align:top}
th{font-size:.66rem;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);font-weight:600}
tbody tr:hover{background:color-mix(in srgb,var(--rule) 25%,transparent)}
td.mono{font-family:ui-monospace,Menlo,monospace;font-size:.79rem}
.gap{color:var(--gap);font-style:italic}
.toolbar{position:sticky;top:0;z-index:5;display:flex;gap:10px;align-items:center;
  background:var(--paper);padding:12px 0;border-bottom:1px solid var(--rule)}
#q{flex:1;font:inherit;font-size:.9rem;padding:.45em .7em;border:1px solid var(--rule-strong);
  border-radius:5px;background:var(--panel);color:var(--ink)}
#qcount{font-family:ui-monospace,Menlo,monospace;font-size:.78rem;color:var(--dim)}
footer{margin-top:64px;padding-top:16px;border-top:3px double var(--rule-strong);
  color:var(--dim);font-size:.84rem}
"""

_JS = """
(function(){
 var root=document.documentElement,btn=document.getElementById('themetoggle'),saved=null;
 try{saved=localStorage.getItem('bth-sci-theme')}catch(e){}
 if(saved)root.setAttribute('data-theme',saved);
 else if(window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches)
   root.setAttribute('data-theme','dark');
 btn.addEventListener('click',function(){
   var n=root.getAttribute('data-theme')==='dark'?'light':'dark';
   root.setAttribute('data-theme',n);
   try{localStorage.setItem('bth-sci-theme',n)}catch(e){}});
 var q=document.getElementById('q'),cnt=document.getElementById('qcount'),
     fns=[].slice.call(document.querySelectorAll('.fn'));
 function run(){
   var t=q.value.trim().toLowerCase(),shown=0;
   fns.forEach(function(el){
     var hit=!t||el.dataset.hay.indexOf(t)>-1;
     el.style.display=hit?'':'none'; if(hit)shown++;});
   document.querySelectorAll('.modblock').forEach(function(m){
     var any=[].slice.call(m.querySelectorAll('.fn')).some(function(e){return e.style.display!=='none'});
     m.style.display=any?'':'none';});
   document.querySelectorAll('.dir').forEach(function(d){
     var any=[].slice.call(d.querySelectorAll('.fn')).some(function(e){return e.style.display!=='none'});
     d.style.display=any?'':'none'; if(t&&any)d.open=true;});
   cnt.textContent=shown+' function'+(shown===1?'':'s');}
 q.addEventListener('input',run); run();
})();
"""


def render() -> str:
    data = scan()
    rev = reverse_index(data)
    sci = {k: v for k, v in data["modules"].items() if v["is_science"]}

    by_dir: dict[str, list[dict]] = {}
    for dotted, m in sorted(sci.items()):
        rest = _short(dotted)
        d = rest.split(".")[0] if "." in rest else ""
        if not d or not (m["functions"] or m["constants"]):
            continue
        by_dir.setdefault(d, []).append(m)

    n_fns = sum(len(m["functions"]) for m in sci.values())
    n_pub = sum(1 for m in sci.values() for f in m["functions"].values()
                if not f["private"])
    cites = {k: v for m in sci.values() for k, v in m["citations"].items()}
    n_gaps = sum(1 for v in cites.values() if v is None)

    out: list[str] = []
    A = out.append
    A('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">')
    A('<meta name="viewport" content="width=device-width, initial-scale=1">')
    A("<title>beamtimehero — science index</title>")
    A(f"<style>{_CSS}</style>\n</head>\n<body>\n<div class=\"wrap\">")

    A('<header><div class="eyebrow">Generated — beamtimehero_cli</div>')
    A('<h1>Science index — <span class="thin">every function, and what uses it</span></h1>')
    A('<p class="lede">The scientific core of the toolbelt: what each function '
      'does, what it is called by, and what it cites. Generated from the source '
      'tree, so a new function appears here by existing. Regenerate with '
      '<code>python -m beamtimehero_cli.docgen_science</code>.</p>')
    A('<div class="statstrip">')
    A(f'<div class="stat"><b>{n_fns}</b><span>functions</span></div>')
    A(f'<div class="stat"><b>{n_pub}</b><span>public</span></div>')
    n_shown = sum(len(v) for v in by_dir.values())
    A(f'<div class="stat"><b>{n_shown}</b><span>modules</span></div>')
    A(f'<div class="stat"><b>{len(cites) - n_gaps}</b><span>cited methods</span></div>')
    A(f'<div class="stat"><b>{n_gaps}</b><span>attribution gaps</span></div>')
    A('<button id="themetoggle">&#9689; theme</button></div></header>')

    A('<div class="therule"><blockquote>Everything under <code>science/</code> '
      'takes <b>numbers in</b> and returns <b>numbers out</b>. No file paths, no '
      'environment variables, no SPEC, no database, no argparse.</blockquote></div>')

    A('<h2><span class="no">01</span> Functions</h2>')
    A('<p class="sectionnote">Grouped by directory, then module, in pipeline '
      'order. &ldquo;Used by&rdquo; is computed from a call graph that follows '
      'indirect routes (tool &rarr; handler &rarr; spec_data &rarr; science), so '
      'a function with no listed tool is very likely genuinely unreached. '
      'Resolution is static, so a call assembled at runtime (getattr, a '
      'name built from a string) is the one thing it cannot follow.</p>')
    A('<div class="toolbar"><input id="q" type="search" '
      'placeholder="Filter functions, modules, docstrings, tool names&hellip;">'
      '<span id="qcount"></span></div>')

    ordered = [d for d in DIR_ORDER if d in by_dir]
    ordered += [d for d in sorted(by_dir) if d not in DIR_ORDER]
    for d in ordered:
        mods = by_dir[d]
        total = sum(len(m["functions"]) for m in mods)
        A(f'<details class="dir" style="--c: var(--c-{d})" open>')
        A(f'<summary><span class="dname">science/{_esc(d)}/</span>'
          f'<span class="chip" style="--c: var(--c-{d})">{len(mods)} modules</span>'
          f'<span class="count">{total} fns</span></summary>')
        if d in DIR_NOTES:
            A(f'<p class="note">{_esc(DIR_NOTES[d])}</p>')
        for m in mods:
            A('<div class="modblock">')
            A('<div class="modhead">'
              f'<span class="mpath">{_esc(_short(m["dotted"]))}</span>'
              f'<span class="mdoc">{_esc(m["doc"])}</span></div>')
            consts = [c for c in m["constants"] if c != "CITATIONS"]
            if consts:
                hay = " ".join([_short(m["dotted"])] + consts).lower()
                A(f'<div class="fn const" data-hay="{_esc(hay)}">')
                A('<p class="users"><b>constants</b> '
                  + ", ".join(f'<code>{_esc(c)}</code>' for c in consts) + "</p>")
                A('<p class="fdoc">Module-level data and defaults. Editing these '
                  'is the most common kind of contribution; nothing here needs a '
                  'call graph to be safe to change, but see "used by" on the '
                  'functions that read them.</p>')
                A("</div>")
            for name, f in sorted(m["functions"].items(),
                                  key=lambda kv: (kv[1]["private"], kv[1]["lineno"])):
                users = sorted(rev.get((m["dotted"], name), ()))
                hay = " ".join([name, _short(m["dotted"]), f["doc"]] + users).lower()
                cls = "fn priv" if f["private"] else "fn"
                A(f'<div class="{cls}" data-hay="{_esc(hay)}">')
                A(f'<span class="sig"><span class="fname">{_esc(name)}</span>'
                  f'{_esc(f["signature"])}</span>')
                if f["doc"]:
                    A(f'<p class="fdoc">{_esc(f["doc"])}</p>')
                if users:
                    shown = ", ".join(_esc(u) for u in users[:6])
                    more = f" +{len(users) - 6} more" if len(users) > 6 else ""
                    A(f'<p class="users"><b>used by</b> {shown}{more}</p>')
                else:
                    A('<p class="users"><span class="none">not reached from any '
                      'catalog tool</span></p>')
                A("</div>")
            A("</div>")
        A("</details>")

    A('<h2><span class="no">02</span> Bibliography</h2>')
    A('<p class="sectionnote">Collected from every module\'s <code>CITATIONS</code> '
      'dict. Entries marked <span class="gap">needs a reference</span> are '
      'implemented but unattributed — filling one in is a welcome contribution.</p>')
    A("<table><thead><tr><th>Method</th><th>Reference</th><th>Module</th></tr>"
      "</thead><tbody>")
    rows = []
    for dotted, m in sorted(sci.items()):
        for what, ref in m["citations"].items():
            rows.append((what, ref, _short(dotted)))
    for what, ref, where in sorted(rows, key=lambda r: (r[1] is None, r[2], r[0])):
        cell = (f'<span class="gap">needs a reference</span>' if ref is None
                else _esc(ref))
        A(f"<tr><td>{_esc(what)}</td><td>{cell}</td>"
          f'<td class="mono">{_esc(where)}</td></tr>')
    A("</tbody></table>")

    A("<footer>Generated by <code>beamtimehero_cli.docgen_science</code> from the "
      "source tree. Layout and conventions: <code>science/README.md</code>. "
      "Contributing: <code>CONTRIBUTING.md</code>. The agent-facing tool catalog "
      'is <a href="tool_catalog.html">tool_catalog.html</a>.</footer>')
    A(f"</div>\n<script>{_JS}</script>\n</body>\n</html>")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m beamtimehero_cli.docgen_science",
        description="Render the science/ package as a static HTML index.",
    )
    parser.add_argument(
        "-o", "--output", default="docs/science_index.html",
        help="Output path (default: docs/science_index.html, relative to cwd).",
    )
    args = parser.parse_args(argv)

    page = render()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)

    data = scan()
    sci = {k: v for k, v in data["modules"].items() if v["is_science"]}
    n_fns = sum(len(m["functions"]) for m in sci.values())
    cites = {k: v for m in sci.values() for k, v in m["citations"].items()}
    gaps = sum(1 for v in cites.values() if v is None)
    print(f"wrote {out} — {n_fns} functions, {len(sci)} modules, "
          f"{len(cites)} citations ({gaps} gaps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
