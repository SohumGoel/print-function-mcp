"""Print-function MCP server: function-aware checks for failed or imperfect FDM prints (Project 2).

Run with MCP Inspector:  uv run mcp dev server.py
Run over stdio:          uv run server.py
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import print_tools as pt

mcp = MCPServer(
    "print-function",
    instructions=(
        "Checks whether an imperfect FDM print can still do its job, and what a failure costs. "
        "Lengths in mm (x, y measured from the part's datum frame), time in hours, mass in grams, "
        "money in USD. Every result has a 'scope' field listing its assumptions; tools never "
        "measure the part themselves, so inputs must come from calipers, a camera system or the slicer."
    ),
)

Mm = lambda lo, hi, desc: Annotated[float, Field(ge=lo, le=hi, description=desc)]
Fastener = Literal["M3", "M4", "M5", "M6", "M8", "M10", "M12"]
Progress = Mm(0, 100, "Share of the print completed when it stopped or failed, %")
PartMass = Mm(1, 5000, "Total filament mass of the full print, g (from the slicer)")
PrintTime = Mm(0.1, 200, "Total print time of the full job, h (from the slicer)")
FilamentCost = Mm(0, 500, "Filament price, USD/kg")
Power = Mm(10, 2000, "Average printer power while printing, W (measure with a plug meter if possible)")
Electricity = Mm(0, 2, "Electricity price, USD/kWh")
MachineCost = Mm(0, 200, "Value of machine time, USD/h; 0 to ignore")


def run(fn, **kwargs):
    """Call a calculation; turn its ValueError into a ToolError the client can read."""
    try:
        return fn(**kwargs)
    except (ValueError, KeyError) as exc:
        raise ToolError(str(exc)) from exc


# ---------- Result and input models ----------

class PositionResult(BaseModel):
    dx_mm: float
    dy_mm: float
    radial_offset_mm: float = Field(description="Distance of the measured axis from nominal, sqrt(dx^2+dy^2)")
    position_deviation_dia_mm: float = Field(description="Position zone diameter needed, 2 x radial offset; this is what is compared with the tolerance")
    bonus_tolerance_mm: float
    allowed_position_tol_mm: float
    margin_mm: float = Field(description="Allowed tolerance minus deviation; negative = out of tolerance")
    in_position_tolerance: bool
    hole_size_at_least_mmc: bool | None
    scope: str


class FastenerFit(BaseModel):
    fastener_major_dia_mm: float
    iso273_hole_dia_mm: dict[str, float]
    target_hole_dia_mm: float
    shortfall_vs_target_mm: float
    bolt_passes: bool
    floating_position_tol_mm: float = Field(description="Position tolerance the hole allows a floating bolt, T = H - F")
    verdict: str
    scope: str


class Waste(BaseModel):
    wasted_filament_g: float
    wasted_time_h: float
    wasted_energy_kwh: float
    wasted_cost_usd: float
    full_print_cost_usd: float
    scope: str


class Feature(BaseModel):
    name: str = Field(description="Label, e.g. 'motor hole A'")
    z_bottom_mm: float = Field(ge=0, le=500, description="Height where the feature starts")
    z_top_mm: float = Field(ge=0, le=500, description="Height where the feature ends")
    position_tol_mm: float = Field(ge=0.01, le=5, description="Position tolerance (diameter) relative to the datums")
    hole_dia_mm: float | None = Field(default=None, ge=0.5, le=50, description="Hole diameter, if the feature is a hole")
    fastener: Fastener | None = Field(default=None, description="Bolt that must pass through the hole")


class FeatureImpact(BaseModel):
    name: str
    status: str
    position_deviation_dia_mm: float
    functional: bool
    step_mm: float | None = None
    clear_through_dia_mm: float | None = None
    bolt_passes: bool | None = None


class ShiftImpact(BaseModel):
    shift_magnitude_mm: float
    features: list[FeatureImpact]
    all_features_functional: bool
    scope: str


class ContinueOrScrap(BaseModel):
    expected_cost_continue_usd: float
    expected_cost_scrap_usd: float
    expected_hours_to_usable_part_continue: float
    expected_hours_to_usable_part_scrap: float
    breakeven_p_usable: float = Field(description="Continuing is cheaper when p_usable_if_continued is above this")
    cheaper_option: Literal["continue", "scrap"]
    scope: str


# ---------- Base tools ----------

@mcp.tool()
def feature_position_check(
    nominal_x_mm: Mm(-500, 500, "Nominal x of the feature axis from the datum frame (CAD/G-code)"),
    nominal_y_mm: Mm(-500, 500, "Nominal y of the feature axis from the datum frame"),
    measured_x_mm: Mm(-500, 500, "Measured x of the feature axis from the same datums"),
    measured_y_mm: Mm(-500, 500, "Measured y of the feature axis from the same datums"),
    position_tol_mm: Mm(0.01, 5, "Position tolerance (zone diameter) at MMC"),
    hole_mmc_dia_mm: Annotated[float | None, Field(ge=0.5, le=50, description="Smallest allowed hole diameter (MMC); give with measured_hole_dia_mm for bonus")] = None,
    measured_hole_dia_mm: Annotated[float | None, Field(ge=0.5, le=50, description="Measured hole diameter")] = None,
) -> PositionResult:
    """GD&T true-position check of a hole or pin axis relative to the datums, with MMC bonus tolerance."""
    return PositionResult(**run(pt.position_check, nominal_x_mm=nominal_x_mm, nominal_y_mm=nominal_y_mm,
                                measured_x_mm=measured_x_mm, measured_y_mm=measured_y_mm,
                                position_tol_mm=position_tol_mm, hole_mmc_dia_mm=hole_mmc_dia_mm,
                                measured_hole_dia_mm=measured_hole_dia_mm))


@mcp.tool()
def fastener_fit_check(
    fastener: Fastener,
    measured_hole_dia_mm: Mm(0.5, 50, "Measured diameter of the printed hole"),
    fit_class: Literal["fine", "medium", "coarse"] = "medium",
) -> FastenerFit:
    """Whether a metric bolt passes through a printed hole, compared with ISO 273 clearance holes."""
    return FastenerFit(**run(pt.fastener_fit, fastener=fastener,
                             measured_hole_dia_mm=measured_hole_dia_mm, fit_class=fit_class))


@mcp.tool()
def failure_waste(
    part_mass_g: PartMass,
    total_print_time_h: PrintTime,
    progress_pct: Progress,
    filament_cost_per_kg: FilamentCost = 20.0,
    printer_power_w: Power = 120.0,
    electricity_cost_per_kwh: Electricity = 0.15,
    machine_cost_per_h: MachineCost = 0.0,
) -> Waste:
    """Filament, machine time, energy and money lost when a print is abandoned partway."""
    return Waste(**run(pt.waste, part_mass_g=part_mass_g, total_print_time_h=total_print_time_h,
                       progress_pct=progress_pct, filament_cost_per_kg=filament_cost_per_kg,
                       printer_power_w=printer_power_w, electricity_cost_per_kwh=electricity_cost_per_kwh,
                       machine_cost_per_h=machine_cost_per_h))


# ---------- New tools ----------

@mcp.tool()
def layer_shift_impact(
    shift_dx_mm: Mm(-50, 50, "Measured x offset of the layers above the shift"),
    shift_dy_mm: Mm(-50, 50, "Measured y offset of the layers above the shift"),
    shift_height_mm: Mm(0, 500, "Height at which the shift happened"),
    features: Annotated[list[Feature], Field(min_length=1, description="Functional features to check")],
) -> ShiftImpact:
    """Which functional features a layer shift moves or splits relative to the datums, and whether each still works.

    Geometry only. To decide whether to keep printing, follow with continue_or_scrap.
    """
    return ShiftImpact(**run(pt.shift_impact, shift_dx_mm=shift_dx_mm, shift_dy_mm=shift_dy_mm,
                             shift_height_mm=shift_height_mm,
                             features=[f.model_dump() for f in features]))


@mcp.tool()
def continue_or_scrap(
    progress_pct: Progress,
    total_print_time_h: PrintTime,
    part_mass_g: PartMass,
    p_usable_if_continued: Mm(0, 1, "Probability the finished part will be usable if the print continues (judgment or from layer_shift_impact)"),
    p_reprint_success: Mm(0.05, 1, "Probability a fresh reprint succeeds") = 0.9,
    filament_cost_per_kg: FilamentCost = 20.0,
    printer_power_w: Power = 120.0,
    electricity_cost_per_kwh: Electricity = 0.15,
    machine_cost_per_h: MachineCost = 0.0,
) -> ContinueOrScrap:
    """Expected cost and hours to one usable part: let the print finish, or scrap now and reprint."""
    return ContinueOrScrap(**run(pt.continue_or_scrap, progress_pct=progress_pct,
                                 total_print_time_h=total_print_time_h, part_mass_g=part_mass_g,
                                 p_usable_if_continued=p_usable_if_continued,
                                 p_reprint_success=p_reprint_success,
                                 filament_cost_per_kg=filament_cost_per_kg, printer_power_w=printer_power_w,
                                 electricity_cost_per_kwh=electricity_cost_per_kwh,
                                 machine_cost_per_h=machine_cost_per_h))


if __name__ == "__main__":
    mcp.run()
