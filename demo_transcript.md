# MCP demo transcript

Server `print-function` over stdio, 2026-11-07 13:14.

**Tools listed by the server:** `feature_position_check`, `fastener_fit_check`, `failure_waste`, `layer_shift_impact`, `continue_or_scrap`

## Base tool (rebuilt from HW4): `feature_position_check`

Request:
```json
{
  "nominal_x_mm": 20,
  "nominal_y_mm": 15,
  "measured_x_mm": 20.12,
  "measured_y_mm": 14.91,
  "position_tol_mm": 0.2,
  "hole_mmc_dia_mm": 3.4,
  "measured_hole_dia_mm": 3.55
}
```

Response (is_error=False):
```
{
  "dx_mm": 0.12,
  "dy_mm": -0.09,
  "radial_offset_mm": 0.15,
  "position_deviation_dia_mm": 0.3,
  "bonus_tolerance_mm": 0.15,
  "allowed_position_tol_mm": 0.35,
  "margin_mm": 0.05,
  "in_position_tolerance": true,
  "hole_size_at_least_mmc": true,
  "scope": "ASME Y14.5 position: deviation = 2*sqrt(dx^2+dy^2); MMC bonus = measured hole - MMC size (holes only). Compare the zone diameter, not the radial offset, with the tolerance. Axis assumed perpendicular to the datum plane; 2D (x, y) only; geometry only, says nothing about strength."
}
```

## Base tool (rebuilt from HW4): `fastener_fit_check`

Request:
```json
{
  "fastener": "M3",
  "measured_hole_dia_mm": 3.25
}
```

Response (is_error=False):
```
{
  "fastener_major_dia_mm": 3.0,
  "iso273_hole_dia_mm": {
    "fine": 3.2,
    "medium": 3.4,
    "coarse": 3.6
  },
  "target_hole_dia_mm": 3.4,
  "shortfall_vs_target_mm": 0.15,
  "bolt_passes": true,
  "floating_position_tol_mm": 0.25,
  "verdict": "ok: between ISO 273 fine and coarse (below the medium hole)",
  "scope": "ISO 273 clearance-hole series; floating-fastener position tolerance T = H - F (hole minus bolt major diameter). Assumes a round, straight hole."
}
```

## Base tool (rebuilt from HW4): `failure_waste`

Request:
```json
{
  "part_mass_g": 85,
  "total_print_time_h": 6,
  "progress_pct": 70
}
```

Response (is_error=False):
```
{
  "wasted_filament_g": 59.5,
  "wasted_time_h": 4.2,
  "wasted_energy_kwh": 0.504,
  "wasted_cost_usd": 1.27,
  "full_print_cost_usd": 1.81,
  "scope": "material and time used scale linearly with progress; constant average printer power; default prices and power are placeholders to replace with measured values"
}
```

## New tool 1: `layer_shift_impact`

Request:
```json
{
  "shift_dx_mm": 0.4,
  "shift_dy_mm": 0.3,
  "shift_height_mm": 10,
  "features": [
    {
      "name": "base mounting hole",
      "z_bottom_mm": 0,
      "z_top_mm": 4,
      "position_tol_mm": 0.3,
      "hole_dia_mm": 3.4,
      "fastener": "M3"
    },
    {
      "name": "motor face hole",
      "z_bottom_mm": 12,
      "z_top_mm": 18,
      "position_tol_mm": 0.3,
      "hole_dia_mm": 3.4,
      "fastener": "M3"
    },
    {
      "name": "through hole for M3 bolt",
      "z_bottom_mm": 0,
      "z_top_mm": 20,
      "position_tol_mm": 1.5,
      "hole_dia_mm": 3.4,
      "fastener": "M3"
    }
  ]
}
```

Response (is_error=False):
```
{
  "shift_magnitude_mm": 0.5,
  "features": [
    {
      "name": "base mounting hole",
      "status": "unaffected",
      "position_deviation_dia_mm": 0.0,
      "functional": true,
      "step_mm": null,
      "clear_through_dia_mm": null,
      "bolt_passes": null
    },
    {
      "name": "motor face hole",
      "status": "moved: whole feature printed after the shift",
      "position_deviation_dia_mm": 1.0,
      "functional": false,
      "step_mm": null,
      "clear_through_dia_mm": null,
      "bolt_passes": null
    },
    {
      "name": "through hole for M3 bolt",
      "status": "split: shift happened partway up this feature",
      "position_deviation_dia_mm": 1.0,
      "functional": false,
      "step_mm": 0.5,
      "clear_through_dia_mm": 2.9,
      "bolt_passes": false
    }
  ],
  "all_features_functional": false,
  "scope": "pure x-y translation of every layer above shift_height_mm; datums are features printed below the shift; vertical cylindrical features; nominal geometry assumed correct before the shift; geometry only: does not check strength, layer adhesion or material behavior"
}
```

## New tool 2: `continue_or_scrap`

Request:
```json
{
  "progress_pct": 60,
  "total_print_time_h": 6,
  "part_mass_g": 85,
  "p_usable_if_continued": 0.05
}
```

Response (is_error=False):
```
{
  "expected_cost_continue_usd": 2.63,
  "expected_cost_scrap_usd": 2.01,
  "expected_hours_to_usable_part_continue": 8.73,
  "expected_hours_to_usable_part_scrap": 6.67,
  "breakeven_p_usable": 0.36,
  "cheaper_option": "scrap",
  "scope": "sunk cost ignored; costs and time scale linearly with progress; reprints are independent with success probability p_reprint_success; p_usable_if_continued is a judgment input"
}
```

## Invalid input (schema): `fastener_fit_check`

Request:
```json
{
  "fastener": "M7",
  "measured_hole_dia_mm": 7.5
}
```

Response (is_error=True):
```
Error executing tool fastener_fit_check: 1 validation error for fastener_fit_checkArguments
fastener
  Input should be 'M3', 'M4', 'M5', 'M6', 'M8', 'M10' or 'M12' [type=literal_error, input_value='M7', input_type=str]
    For further information visit https://errors.pydantic.dev/2.14/v/literal_error
```

## Invalid input (server check): `layer_shift_impact`

Request:
```json
{
  "shift_dx_mm": 0.4,
  "shift_dy_mm": 0,
  "shift_height_mm": 10,
  "features": [
    {
      "name": "hole",
      "z_bottom_mm": 8,
      "z_top_mm": 2,
      "position_tol_mm": 0.3
    }
  ]
}
```

Response (is_error=True):
```
Error executing tool layer_shift_impact: hole: z_top_mm must be greater than z_bottom_mm
```
