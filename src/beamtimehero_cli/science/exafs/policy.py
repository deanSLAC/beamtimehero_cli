"""EXAFS analysis policy — the k-space defaults, in one place.

These were hard-coded at every call site in the tool handlers (the k-weight
default appeared five times). Changing a default is now a one-line edit here.
"""
from __future__ import annotations

# k-weighting applied to chi(k) before the Fourier transform. k^2 is the
# conventional compromise: it balances the low-k (light-scatterer) and high-k
# (heavy-scatterer) contributions without over-amplifying high-k noise.
DEFAULT_KWEIGHT = 2

# Lower k bound for the FT window. Below ~2 A^-1 the AUTOBK background and the
# XANES region are not cleanly separable.
DEFAULT_KMIN = 2.0

# Upper k bound. None = use the full measured range (data quality, not policy,
# should set the ceiling).
DEFAULT_KMAX = None

# Hanning window taper width (A^-1) at each end of the k range.
DEFAULT_DK = 1.0

# AUTOBK R_bkg (A): the below-first-shell distance the spline is allowed to
# follow. 1.0 A is the standard choice for a first-shell-and-beyond fit.
DEFAULT_RBKG = 1.0

# ---------------------------------------------------------------------------
# CITATIONS — method -> reference. ``None`` means the method is implemented
# but not yet attributed; those surface as gaps on the generated science
# index, and filling one in is a welcome contribution. See science/README.md.
# ---------------------------------------------------------------------------

CITATIONS = {
    "k^2 weighting as the default": None,
    "Default k range and window taper": None,
    "Default AUTOBK R_bkg": None,
}
