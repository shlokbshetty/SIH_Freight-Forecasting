"""
HeadlineGenerator — Dynamic narrative summary for Spot vs. CVC financial decisions.

Generates a single-sentence headline that communicates the key outcome
(who wins, by how much, and what probability threshold to watch).

Requirements: 1.4
"""


class HeadlineGenerator:
    """
    Generates human-readable financial headline summaries for Spot vs. CVC comparisons.

    Headline format:
      CVC favorable:  "CVC saves ₹{X} Cr across {N} voyages. Spot only wins if rates fall below ${Y}/T —
                       our forecast puts that probability at {Z}%."
      Spot favorable: "Spot saves ₹{X} Cr across {N} voyages. CVC only wins if rates rise above ${Y}/T —
                       our forecast puts that probability at {Z}%."
    """

    @staticmethod
    def generate_headline(
        is_cvc_favorable: bool,
        delta_cr: float,
        num_voyages: int,
        breakeven_rate: float,
        breakeven_probability_pct: float,
    ) -> str:
        """
        Generates the financial outcome headline.

        Args:
            is_cvc_favorable:          True when CVC total cost <= spot total cost.
            delta_cr:                  Magnitude of savings in Indian Crores (₹).
                                       Formatted to 1 decimal place.
            num_voyages:               Number of voyages in the contract window.
            breakeven_rate:            Spot rate threshold ($/T) at which spot equals CVC.
                                       Formatted to 2 decimal places.
            breakeven_probability_pct: P(Spot < breakeven_rate) as percentage [0–100].
                                       When CVC is favorable, this is the probability spot
                                       falls below threshold (spot would win).
                                       When spot is favorable, this is P(spot < breakeven),
                                       so the relevant probability is (100 - breakeven_probability_pct).

        Returns:
            Formatted headline string.
        """
        delta_str = f"₹{delta_cr:.1f} Cr"
        rate_str = f"${breakeven_rate:.2f}/T"

        if is_cvc_favorable:
            # P(spot falls below breakeven) = P(spot wins if CVC taken)
            prob_int = round(breakeven_probability_pct)
            return (
                f"CVC saves {delta_str} across {num_voyages} voyages. "
                f"Spot only wins if rates fall below {rate_str} — "
                f"our forecast puts that probability at {prob_int}%."
            )
        else:
            # P(rates rise above breakeven) = 100 - P(spot < breakeven)
            prob_int = round(100.0 - breakeven_probability_pct)
            return (
                f"Spot saves {delta_str} across {num_voyages} voyages. "
                f"CVC only wins if rates rise above {rate_str} — "
                f"our forecast puts that probability at {prob_int}%."
            )
