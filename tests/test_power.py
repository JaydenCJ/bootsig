"""Tests for minimum-detectable-effect and required-n calculations.

The closed-form values here are checked against the textbook constants
(z_0.975 + z_0.8 = 2.8016), so a regression in the formula cannot hide.
"""

from __future__ import annotations

import math

import pytest

from bootsig.errors import UsageError
from bootsig.power import mde, required_n

Z_TOTAL_05_80 = 1.9599640 + 0.8416212  # z_{0.975} + z_{0.8}


def test_mde_paired_matches_textbook_formula_and_scales_with_sqrt_n():
    assert mde(1.0, 100) == pytest.approx(Z_TOTAL_05_80 / 10.0, abs=1e-6)
    assert mde(1.0, 400) == pytest.approx(mde(1.0, 100) / 2.0)


def test_mde_unpaired_is_sqrt2_times_paired():
    paired = mde(0.5, 64, design="paired")
    unpaired = mde(0.5, 64, design="unpaired")
    assert unpaired == pytest.approx(paired * math.sqrt(2.0))


def test_required_n_known_value_and_power_monotonicity():
    # ((2.8016 * 0.5) / 0.1)^2 = 196.2 -> 197 pairs.
    assert required_n(0.5, 0.1) == 197
    assert required_n(0.5, 0.1, power=0.9) > required_n(0.5, 0.1, power=0.8)


def test_required_n_unpaired_doubles_the_paired_requirement():
    paired = required_n(0.5, 0.1, design="paired")
    unpaired = required_n(0.5, 0.1, design="unpaired")
    assert unpaired in (2 * paired - 1, 2 * paired, 2 * paired + 1)  # ceil rounding


def test_mde_and_required_n_round_trip():
    detectable = mde(0.42, 150)
    assert required_n(0.42, detectable) in (149, 150, 151)


def test_zero_sd_means_anything_is_detectable():
    assert mde(0.0, 50) == 0.0
    assert required_n(0.0, 0.01) == 2


def test_invalid_parameters_raise_usage_errors():
    with pytest.raises(UsageError, match="target difference"):
        required_n(0.5, 0.0)
    with pytest.raises(UsageError, match="alpha"):
        mde(0.5, 50, alpha=0.0)
    with pytest.raises(UsageError, match="power"):
        mde(0.5, 50, power=1.0)
    with pytest.raises(UsageError, match="design"):
        mde(0.5, 50, design="crossover")
    with pytest.raises(UsageError, match="n must be"):
        mde(0.5, 1)
