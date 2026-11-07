"""Function-aware checks for failed or imperfect FDM prints (Project 2).

Pure functions with no MCP code; server.py wraps them as tools. Every function checks its
inputs and raises ValueError instead of returning a plausible-looking number.
Lengths in mm, time in hours, mass in grams, money in USD.
"""

import math

# ISO 273 clearance holes (mm): fastener → (major diameter, fine, medium, coarse).
ISO_273 = {
    "M3": (3.0, 3.2, 3.4, 3.6), "M4": (4.0, 4.3, 4.5, 4.8), "M5": (5.0, 5.3, 5.5, 5.8),
    "M6": (6.0, 6.4, 6.6, 7.0), "M8": (8.0, 8.4, 9.0, 10.0), "M10": (10.0, 10.5, 11.0, 12.0),
    "M12": (12.0, 13.0, 13.5, 14.5),
}
FIT_CLASSES = ("fine", "medium", "coarse")


def check_range(name, value, low, high):
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(value) or not low <= value <= high):
        raise ValueError(f"{name} must be a number from {low} to {high}; got {value!r}")


def r(x, n=3):
    return round(float(x), n)


# ---------- Base tools ----------

def position_check(nominal_x_mm, nominal_y_mm, measured_x_mm, measured_y_mm, position_tol_mm,
                   hole_mmc_dia_mm=None, measured_hole_dia_mm=None):
    """GD&T true position of a hole axis relative to the datum frame, with MMC bonus for holes."""
    for name, v in [("nominal_x_mm", nominal_x_mm), ("nominal_y_mm", nominal_y_mm),
                    ("measured_x_mm", measured_x_mm), ("measured_y_mm", measured_y_mm)]:
        check_range(name, v, -500, 500)
    check_range("position_tol_mm", position_tol_mm, 0.01, 5)
    if (hole_mmc_dia_mm is None) != (measured_hole_dia_mm is None):
        raise ValueError("give both hole_mmc_dia_mm and measured_hole_dia_mm, or neither")
    dx, dy = measured_x_mm - nominal_x_mm, measured_y_mm - nominal_y_mm
    deviation = 2 * math.hypot(dx, dy)          # diameter of the zone the axis actually needs
    bonus, size_ok = 0.0, None
    if hole_mmc_dia_mm is not None:
        check_range("hole_mmc_dia_mm", hole_mmc_dia_mm, 0.5, 50)
        check_range("measured_hole_dia_mm", measured_hole_dia_mm, 0.5, 50)
        size_ok = measured_hole_dia_mm >= hole_mmc_dia_mm
        bonus = max(0.0, measured_hole_dia_mm - hole_mmc_dia_mm)
    allowed = position_tol_mm + bonus
    return {
        "dx_mm": r(dx), "dy_mm": r(dy),
        "position_deviation_dia_mm": r(deviation),
        "bonus_tolerance_mm": r(bonus),
        "allowed_position_tol_mm": r(allowed),
        "margin_mm": r(allowed - deviation),
        "in_position_tolerance": deviation <= allowed + 1e-9,
        "hole_size_at_least_mmc": size_ok,
        "scope": ("ASME Y14.5 position: deviation = 2*sqrt(dx^2+dy^2); MMC bonus = measured hole - MMC size "
                  "(holes only). Measured axis assumed perpendicular to the datum plane; 2D (x, y) only."),
    }


def fastener_fit(fastener, measured_hole_dia_mm, fit_class="medium"):
    """Will a metric bolt pass through a printed hole, and how does the hole compare with ISO 273?"""
    key = str(fastener).strip().upper()
    if key not in ISO_273:
        raise ValueError(f"fastener must be one of {', '.join(ISO_273)}; got {fastener!r}")
    if fit_class not in FIT_CLASSES:
        raise ValueError(f"fit_class must be one of {', '.join(FIT_CLASSES)}; got {fit_class!r}")
    check_range("measured_hole_dia_mm", measured_hole_dia_mm, 0.5, 50)
    major, *classes = ISO_273[key]
    target = classes[FIT_CLASSES.index(fit_class)]
    h = measured_hole_dia_mm
    if h <= major:
        verdict = "blocked: bolt will not pass without drilling"
    elif h < classes[0]:
        verdict = "tight: passes, but smaller than the ISO 273 fine hole"
    elif h <= classes[2]:
        verdict = f"ok: between ISO 273 fine and coarse ({'meets' if h >= target else 'below'} the {fit_class} hole)"
    else:
        verdict = "oversize: looser than the ISO 273 coarse hole"
    return {
        "fastener_major_dia_mm": major,
        "iso273_hole_dia_mm": {"fine": classes[0], "medium": classes[1], "coarse": classes[2]},
        "target_hole_dia_mm": target,
        "shortfall_vs_target_mm": r(max(0.0, target - h)),
        "bolt_passes": h > major,
        "floating_position_tol_mm": r(max(0.0, h - major)),
        "verdict": verdict,
        "scope": ("ISO 273 clearance-hole series; floating-fastener position tolerance T = H - F "
                  "(hole minus bolt major diameter). Assumes a round, straight hole."),
    }


def cost_inputs(part_mass_g, total_print_time_h, filament_cost_per_kg, printer_power_w,
                electricity_cost_per_kwh, machine_cost_per_h):
    check_range("part_mass_g", part_mass_g, 1, 5000)
    check_range("total_print_time_h", total_print_time_h, 0.1, 200)
    check_range("filament_cost_per_kg", filament_cost_per_kg, 0, 500)
    check_range("printer_power_w", printer_power_w, 10, 2000)
    check_range("electricity_cost_per_kwh", electricity_cost_per_kwh, 0, 2)
    check_range("machine_cost_per_h", machine_cost_per_h, 0, 200)
    material = part_mass_g / 1000 * filament_cost_per_kg
    energy_kwh = printer_power_w * total_print_time_h / 1000
    full_cost = material + energy_kwh * electricity_cost_per_kwh + machine_cost_per_h * total_print_time_h
    return full_cost, energy_kwh


def waste(part_mass_g, total_print_time_h, progress_pct, filament_cost_per_kg=20.0,
          printer_power_w=120.0, electricity_cost_per_kwh=0.15, machine_cost_per_h=0.0):
    """Filament, time, energy and money lost when a print is abandoned at progress_pct."""
    check_range("progress_pct", progress_pct, 0, 100)
    full_cost, full_kwh = cost_inputs(part_mass_g, total_print_time_h, filament_cost_per_kg,
                                      printer_power_w, electricity_cost_per_kwh, machine_cost_per_h)
    f = progress_pct / 100
    return {
        "wasted_filament_g": r(part_mass_g * f, 1),
        "wasted_time_h": r(total_print_time_h * f, 2),
        "wasted_energy_kwh": r(full_kwh * f, 3),
        "wasted_cost_usd": r(full_cost * f, 2),
        "full_print_cost_usd": r(full_cost, 2),
        "scope": ("material and time used scale linearly with progress; constant average printer power; "
                  "default prices and power are placeholders to replace with measured values"),
    }


# ---------- New tools ----------

def shift_impact(shift_dx_mm, shift_dy_mm, shift_height_mm, features):
    """Effect of a layer shift on each functional feature, relative to datums printed below it."""
    check_range("shift_dx_mm", shift_dx_mm, -50, 50)
    check_range("shift_dy_mm", shift_dy_mm, -50, 50)
    check_range("shift_height_mm", shift_height_mm, 0, 500)
    if not features:
        raise ValueError("features must list at least one functional feature")
    s = math.hypot(shift_dx_mm, shift_dy_mm)
    results = []
    for i, f in enumerate(features):
        name = f.get("name") or f"feature_{i}"
        z0, z1, tol = f["z_bottom_mm"], f["z_top_mm"], f["position_tol_mm"]
        check_range(f"{name}.z_bottom_mm", z0, 0, 500)
        check_range(f"{name}.z_top_mm", z1, 0, 500)
        check_range(f"{name}.position_tol_mm", tol, 0.01, 5)
        if z1 <= z0:
            raise ValueError(f"{name}: z_top_mm must be greater than z_bottom_mm")
        hole, fastener = f.get("hole_dia_mm"), f.get("fastener")
        row = {"name": name}
        if z1 <= shift_height_mm:
            row.update(status="unaffected", position_deviation_dia_mm=0.0, functional=True)
        elif z0 >= shift_height_mm:
            dev = 2 * s
            row.update(status="moved: whole feature printed after the shift",
                       position_deviation_dia_mm=r(dev), functional=dev <= tol)
        else:
            # Bore split by the shift: the straight through-opening shrinks by the shift magnitude.
            row.update(status="split: shift happened partway up this feature",
                       position_deviation_dia_mm=r(2 * s), step_mm=r(s))
            if hole is not None:
                check_range(f"{name}.hole_dia_mm", hole, 0.5, 50)
                clear = hole - s
                row["clear_through_dia_mm"] = r(clear)
                if fastener is not None:
                    major = ISO_273.get(str(fastener).upper(), (None,))[0]
                    if major is None:
                        raise ValueError(f"{name}.fastener must be one of {', '.join(ISO_273)}")
                    row["bolt_passes"] = clear > major
            row["functional"] = (2 * s <= tol) and row.get("bolt_passes", True)
        results.append(row)
    return {
        "shift_magnitude_mm": r(s),
        "features": results,
        "all_features_functional": all(x["functional"] for x in results),
        "scope": ("pure x-y translation of every layer above shift_height_mm; datums are features printed "
                  "below the shift; vertical cylindrical features; nominal geometry assumed correct before the shift"),
    }


def continue_or_scrap(progress_pct, total_print_time_h, part_mass_g, p_usable_if_continued,
                      p_reprint_success=0.9, filament_cost_per_kg=20.0, printer_power_w=120.0,
                      electricity_cost_per_kwh=0.15, machine_cost_per_h=0.0):
    """Expected cost and time to one usable part: finish this print or scrap it now and reprint."""
    check_range("progress_pct", progress_pct, 0, 100)
    check_range("p_usable_if_continued", p_usable_if_continued, 0, 1)
    check_range("p_reprint_success", p_reprint_success, 0.05, 1)
    full_cost, _ = cost_inputs(part_mass_g, total_print_time_h, filament_cost_per_kg,
                               printer_power_w, electricity_cost_per_kwh, machine_cost_per_h)
    remaining = 1 - progress_pct / 100
    p, pr = p_usable_if_continued, p_reprint_success
    # Reprints repeat until one succeeds: expected cost of a fresh good part = full / pr.
    fresh_cost, fresh_time = full_cost / pr, total_print_time_h / pr
    cont_cost = remaining * full_cost + (1 - p) * fresh_cost
    cont_time = remaining * total_print_time_h + (1 - p) * fresh_time
    breakeven = remaining * pr          # continue is cheaper when p_usable > this
    return {
        "expected_cost_continue_usd": r(cont_cost, 2),
        "expected_cost_scrap_usd": r(fresh_cost, 2),
        "expected_hours_to_usable_part_continue": r(cont_time, 2),
        "expected_hours_to_usable_part_scrap": r(fresh_time, 2),
        "breakeven_p_usable": r(breakeven, 3),
        "cheaper_option": "continue" if cont_cost < fresh_cost else "scrap",
        "scope": ("sunk cost ignored; costs and time scale linearly with progress; reprints are independent "
                  "with success probability p_reprint_success; p_usable_if_continued is a judgment input"),
    }
