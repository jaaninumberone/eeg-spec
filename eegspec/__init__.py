"""eeg-spec — reference implementation of a device-agnostic ADS1299 EEG chain.

Nothing here carries a device constant. Every parameter comes from a device profile, and
a field the profile marks unverified stops the run rather than being guessed.
"""
from . import dsp, io, metrics, pipeline, profile, quality  # noqa: F401

__all__ = ["dsp", "io", "metrics", "pipeline", "profile", "quality"]
