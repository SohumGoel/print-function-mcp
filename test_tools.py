"""Independent checks against hand calculations and ISO 273. Run with `uv run pytest -q`."""

import pytest

import print_tools as pt


def test_position_with_mmc_bonus():
    # dx = 0.12, dy = -0.09 → 2*sqrt(0.0144+0.0081) = 2*0.15 = 0.30; bonus 3.55-3.40 = 0.15; allowed 0.35
    r = pt.position_check(20, 15, 20.12, 14.91, 0.20, hole_mmc_dia_mm=3.40, measured_hole_dia_mm=3.55)
    assert r["radial_offset_mm"] == 0.15 and r["position_deviation_dia_mm"] == 0.30
    assert r["allowed_position_tol_mm"] == 0.35
    assert r["in_position_tolerance"] and r["margin_mm"] == 0.05


def test_position_without_bonus_fails():
    r = pt.position_check(20, 15, 20.12, 14.91, 0.20)
    assert not r["in_position_tolerance"] and r["margin_mm"] == -0.10


def test_fastener_fit_iso273():
    r = pt.fastener_fit("M3", 3.25, "medium")   # between fine 3.2 and medium 3.4
    assert r["bolt_passes"] and r["shortfall_vs_target_mm"] == 0.15 and r["floating_position_tol_mm"] == 0.25
    assert pt.fastener_fit("M3", 2.95)["verdict"].startswith("blocked")
    assert pt.fastener_fit("M8", 10.5)["verdict"].startswith("oversize")


def test_waste_by_hand():
    # 85 g, 6 h, 70%: material 1.70 + energy 0.72 kWh*0.15 = 0.108 → full 1.808; wasted 0.7*1.808 = 1.27
    r = pt.waste(85, 6, 70)
    assert r["wasted_filament_g"] == 59.5 and r["wasted_time_h"] == 4.2
    assert r["wasted_energy_kwh"] == 0.504 and r["wasted_cost_usd"] == 1.27


def test_continue_or_scrap_by_hand():
    # full 1.808; fresh = 1.808/0.9 = 2.009; continue = 0.4*1.808 + 0.3*2.009 = 1.326; breakeven 0.4*0.9 = 0.36
    r = pt.continue_or_scrap(60, 6, 85, 0.7)
    assert r["expected_cost_continue_usd"] == 1.33 and r["expected_cost_scrap_usd"] == 2.01
    assert r["breakeven_p_usable"] == 0.36 and r["cheaper_option"] == "continue"
    assert pt.continue_or_scrap(60, 6, 85, 0.3)["cheaper_option"] == "scrap"


def test_shift_impact_cases():
    feats = [
        {"name": "base hole", "z_bottom_mm": 0, "z_top_mm": 4, "position_tol_mm": 0.3},
        {"name": "upper hole", "z_bottom_mm": 12, "z_top_mm": 18, "position_tol_mm": 0.3},
        {"name": "through hole", "z_bottom_mm": 0, "z_top_mm": 20, "position_tol_mm": 1.5,
         "hole_dia_mm": 3.4, "fastener": "M3"},
    ]
    r = pt.shift_impact(0.4, 0.3, 10, feats)    # shift magnitude 0.5
    base, upper, through = r["features"]
    assert r["shift_magnitude_mm"] == 0.5
    assert base["functional"] and base["status"] == "unaffected"
    assert upper["position_deviation_dia_mm"] == 1.0 and not upper["functional"]
    assert through["clear_through_dia_mm"] == 2.9 and through["bolt_passes"] is False
    assert not r["all_features_functional"]


@pytest.mark.parametrize("call", [
    lambda: pt.fastener_fit("M7", 7.5),
    lambda: pt.position_check(0, 0, 0.1, 0, 0.2, hole_mmc_dia_mm=3.4),
    lambda: pt.waste(85, 6, 120),
    lambda: pt.shift_impact(0.4, 0, 10, [{"name": "x", "z_bottom_mm": 5, "z_top_mm": 2, "position_tol_mm": 0.3}]),
    lambda: pt.continue_or_scrap(60, 6, 85, 1.4),
])
def test_invalid_inputs_raise(call):
    with pytest.raises(ValueError):
        call()
