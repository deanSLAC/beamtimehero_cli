"""X-ray Raman scattering (non-resonant inelastic scattering) on the loss axis.

Pipeline order: ``calibrate`` (elastic line -> energy-loss axis, momentum
transfer) -> ``reduce`` (crystal averaging/summing, Compton background, area
normalization) -> ``descriptors`` -> ``interpret``.

Kept separate from ``xas/`` because the XAS defaults are actively wrong here:
there is no edge step to anchor to, and the signal sits on a Compton
background. See ``beamtimehero ref counter-selection``.
"""
