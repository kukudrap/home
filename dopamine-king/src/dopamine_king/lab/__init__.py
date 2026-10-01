"""The Lab: statistics for honest experimentation."""
from .ab import (
    ABResult, BayesResult, bayes_ab, holm_bonferroni, peeking_false_positive_rate, sample_size_per_arm,
    two_proportion_test, wilson_interval,
)
from .bandit import POLICIES, SimResult, compare_policies, simulate
from .sim import AudienceSimulator

__all__ = [
    "ABResult", "BayesResult", "bayes_ab", "holm_bonferroni", "peeking_false_positive_rate",
    "sample_size_per_arm", "two_proportion_test", "wilson_interval", "POLICIES", "SimResult",
    "compare_policies", "simulate", "AudienceSimulator",
]
