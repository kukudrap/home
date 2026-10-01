"""Multi-armed bandits: allocate traffic to winners while still learning (variable reward done honestly)."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Sequence


class Policy:
    name = "base"

    def __init__(self, n_arms: int) -> None:
        self.n = n_arms
        self.pulls = [0] * n_arms
        self.wins = [0] * n_arms

    def select(self, rng: random.Random) -> int:
        raise NotImplementedError

    def update(self, arm: int, reward: int) -> None:
        self.pulls[arm] += 1
        self.wins[arm] += reward


class Uniform(Policy):
    name = "uniform"

    def select(self, rng: random.Random) -> int:
        return sum(self.pulls) % self.n


class EpsilonGreedy(Policy):
    name = "epsilon"

    def __init__(self, n_arms: int, epsilon: float = 0.1) -> None:
        super().__init__(n_arms)
        self.epsilon = epsilon

    def select(self, rng: random.Random) -> int:
        if rng.random() < self.epsilon or not all(self.pulls):
            return rng.randrange(self.n)
        return max(range(self.n), key=lambda i: self.wins[i] / self.pulls[i])


class UCB1(Policy):
    name = "ucb1"

    def select(self, rng: random.Random) -> int:
        for i in range(self.n):
            if self.pulls[i] == 0:
                return i
        total = sum(self.pulls)
        return max(range(self.n), key=lambda i: self.wins[i] / self.pulls[i] + math.sqrt(2 * math.log(total) / self.pulls[i]))


class Thompson(Policy):
    name = "thompson"

    def __init__(self, n_arms: int, prior: tuple[float, float] = (1.0, 1.0)) -> None:
        super().__init__(n_arms)
        self.prior = prior

    def select(self, rng: random.Random) -> int:
        draws = [rng.betavariate(self.prior[0] + self.wins[i], self.prior[1] + self.pulls[i] - self.wins[i]) for i in range(self.n)]
        return max(range(self.n), key=draws.__getitem__)

    def posterior_means(self) -> list[float]:
        return [(self.prior[0] + self.wins[i]) / (self.prior[0] + self.prior[1] + self.pulls[i]) for i in range(self.n)]


POLICIES = {"uniform": Uniform, "epsilon": EpsilonGreedy, "ucb1": UCB1, "thompson": Thompson}


@dataclass
class SimResult:
    policy: str
    rounds: int
    pulls: list[int]
    conversions: int
    regret: float                         # expected conversions lost versus always playing the best arm
    best_arm_share: float
    regret_curve: list[tuple[int, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "policy": self.policy, "rounds": self.rounds, "pulls": self.pulls, "conversions": self.conversions,
            "regret": round(self.regret, 3), "best_arm_share": round(self.best_arm_share, 4),
            "regret_curve": [(r, round(v, 3)) for r, v in self.regret_curve],
        }


def simulate(true_rates: Sequence[float], rounds: int, policy: str = "thompson", seed: int = 0, curve_points: int = 50) -> SimResult:
    rng = random.Random(seed)
    pol = POLICIES[policy](len(true_rates))
    best = max(true_rates)
    regret = 0.0
    conversions = 0
    curve: list[tuple[int, float]] = []
    step = max(1, rounds // curve_points)
    for t in range(1, rounds + 1):
        arm = pol.select(rng)
        reward = 1 if rng.random() < true_rates[arm] else 0
        pol.update(arm, reward)
        conversions += reward
        regret += best - true_rates[arm]
        if t % step == 0 or t == rounds:
            curve.append((t, regret))
    best_arm = true_rates.index(best)
    return SimResult(policy, rounds, pol.pulls, conversions, regret, pol.pulls[best_arm] / rounds, curve)


def compare_policies(true_rates: Sequence[float], rounds: int, policies: Sequence[str] = ("uniform", "epsilon", "ucb1", "thompson"), seeds: int = 20) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for name in policies:
        runs = [simulate(true_rates, rounds, name, seed=s, curve_points=1) for s in range(seeds)]
        out[name] = {
            "mean_regret": sum(r.regret for r in runs) / seeds,
            "mean_best_arm_share": sum(r.best_arm_share for r in runs) / seeds,
            "mean_conversions": sum(r.conversions for r in runs) / seeds,
        }
    return out
