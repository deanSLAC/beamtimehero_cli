"""Preferred emission line (Siegbahn) per absorption edge.

Used to centre the MBACK error-function step. Falls back to the strongest
line starting with the edge letter, then to the edge energy itself.

Source: xraydb's tabulated X-ray emission lines.
"""
from __future__ import annotations


# Preferred emission line (Siegbahn) per edge, used to centre the MBACK
# error-function step. Falls back to the strongest line starting with the
# edge letter, then to the edge energy itself.
_EDGE_EMISSION_LINES = {
    "K": ("Ka1", "Ka2"),
    "L1": ("Lb3", "Lb4"),
    "L2": ("Lb1",),
    "L3": ("La1", "La2"),
    "M4": ("Ma1", "Ma", "Mb"),
    "M5": ("Ma1", "Ma"),
}

def emission_energy_ev(element: str, edge: str) -> float | None:
    """Strongest fluorescence-line energy (eV) for an edge, via xraydb.

    Returns ``None`` if no line can be resolved (the caller falls back to
    the edge energy). Never raises.
    """
    try:
        import xraydb
        lines = xraydb.xray_lines(element)
    except Exception:
        return None
    if not lines:
        return None
    for name in _EDGE_EMISSION_LINES.get(edge.upper(), ()):
        if name in lines:
            return float(lines[name].energy)
    letter = edge[:1].upper()
    cand = [ln for nm, ln in lines.items() if nm.startswith(letter)]
    if cand:
        return float(max(cand, key=lambda ln: ln.intensity).energy)
    return None
