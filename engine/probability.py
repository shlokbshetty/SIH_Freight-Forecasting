"""
ProbabilityCalculator — Empirical Break-Even CDF Engine.

Computes P(Spot Rate < Break-Even Rate) using the implied Gaussian distribution
calibrated from ML quantile spread (p90 - p10) / 2.563 = sigma.

Requirements: 1.2, 1.8
"""

from scipy.stats import norm


class ProbabilityCalculator:
    """
    Computes the probability that spot rates fall below the CVC break-even threshold.

    Uses a Gaussian CDF where the distribution parameters (mean, sigma) are derived
    from the ML multi-quantile forecast: sigma = (p90 - p10) / 2.563, where 2.563
    is 2 × 1.2816 (z-score for 80% span).
    """

    @staticmethod
    def calculate_breakeven_probability(
        breakeven_rate: float,
        mean: float,
        sigma: float,
    ) -> float:
        """
        Computes P(Spot Rate <= break_even_rate) as a percentage using Normal CDF.

        Formula:
            z = (breakeven_rate - mean) / sigma
            probability_pct = norm.cdf(z) × 100.0

        Args:
            breakeven_rate: The CVC break-even spot rate threshold ($/T).
                            If spot rate falls below this, CVC becomes unfavorable.
            mean:           Mean forecasted spot rate from ML p50 predictions ($/T).
            sigma:          Implied standard deviation derived from ML quantile spread.
                            sigma = (p90 - p10) / 2.563  (minimum clamped to 0.5).

        Returns:
            Probability in [0.0, 100.0] — rounded to 1 decimal place.
        """
        if sigma <= 0.0:
            return 100.0 if mean <= breakeven_rate else 0.0

        z = (breakeven_rate - mean) / sigma
        prob = float(norm.cdf(z)) * 100.0
        return max(0.0, min(100.0, round(prob, 1)))
