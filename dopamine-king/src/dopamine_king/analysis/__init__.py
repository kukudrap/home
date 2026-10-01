"""Analysis stack: success labels, benchmarks, pattern mining, calibration and comparison."""
from .benchmark import Benchmark, ItemAnalysis, analyze_items
from .calibrate import Calibration, calibrate_weights, win_probability
from .compare import Comparison, compare_hooks
from .patterns import Pattern, mine_patterns
from .success import derived_signals, success_index

__all__ = [
    "Benchmark", "ItemAnalysis", "analyze_items", "Calibration", "calibrate_weights", "win_probability",
    "Comparison", "compare_hooks", "Pattern", "mine_patterns", "derived_signals", "success_index",
]
