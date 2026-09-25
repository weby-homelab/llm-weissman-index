"""Reference implementation of the LLM Weissman Index."""

from .formula import compute_lwi
from .models import ComparisonInput, Measurement

__all__ = ["ComparisonInput", "Measurement", "compute_lwi"]
__version__ = "0.1.0"
