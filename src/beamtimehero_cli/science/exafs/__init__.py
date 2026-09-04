"""EXAFS k-space analysis: chi(k) extraction and Fourier transforms.

Pipeline order: ``kspace`` (E <-> k) -> ``background`` (AUTOBK-lite spline
removal) -> ``fourier`` (windowed FT into R space).

``policy`` holds the k-space defaults (k-weight, k range, window taper, R_bkg).
"""
