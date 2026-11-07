"""Demo client: launches server.py over stdio, calls tools, saves demo_transcript.md.

Run: uv run demo_client.py
"""

import asyncio
import json
import sys
from datetime import datetime

from mcp import Client, StdioServerParameters

# Example case: an 85 g, 6 h motor bracket with a 0.5 mm layer shift detected at 10 mm (60% done).
# The shift check finds broken features, so the scrap decision uses a low usable probability.
FEATURES = [
    {"name": "base mounting hole", "z_bottom_mm": 0, "z_top_mm": 4, "position_tol_mm": 0.3,
     "hole_dia_mm": 3.4, "fastener": "M3"},
    {"name": "motor face hole", "z_bottom_mm": 12, "z_top_mm": 18, "position_tol_mm": 0.3,
     "hole_dia_mm": 3.4, "fastener": "M3"},
    {"name": "through hole for M3 bolt", "z_bottom_mm": 0, "z_top_mm": 20, "position_tol_mm": 1.5,
     "hole_dia_mm": 3.4, "fastener": "M3"},
]

CALLS = [
    ("Base tool", "feature_position_check",
     {"nominal_x_mm": 20, "nominal_y_mm": 15, "measured_x_mm": 20.12, "measured_y_mm": 14.91,
      "position_tol_mm": 0.2, "hole_mmc_dia_mm": 3.4, "measured_hole_dia_mm": 3.55}),
    ("Base tool", "fastener_fit_check", {"fastener": "M3", "measured_hole_dia_mm": 3.25}),
    ("Base tool", "failure_waste", {"part_mass_g": 85, "total_print_time_h": 6, "progress_pct": 70}),
    ("New tool 1", "layer_shift_impact",
     {"shift_dx_mm": 0.4, "shift_dy_mm": 0.3, "shift_height_mm": 10, "features": FEATURES}),
    ("New tool 2", "continue_or_scrap",
     {"progress_pct": 60, "total_print_time_h": 6, "part_mass_g": 85, "p_usable_if_continued": 0.05}),
    ("Invalid input (schema)", "fastener_fit_check", {"fastener": "M7", "measured_hole_dia_mm": 7.5}),
    ("Invalid input (server check)", "layer_shift_impact",
     {"shift_dx_mm": 0.4, "shift_dy_mm": 0, "shift_height_mm": 10,
      "features": [{"name": "hole", "z_bottom_mm": 8, "z_top_mm": 2, "position_tol_mm": 0.3}]}),
]


async def main():
    server = StdioServerParameters(command=sys.executable, args=["server.py"])
    lines = [f"# MCP demo transcript\n\nServer `print-function` over stdio, {datetime.now():%Y-%m-%d %H:%M}.\n"]
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
        lines.append("**Tools listed by the server:** " + ", ".join(f"`{t.name}`" for t in tools) + "\n")
        for label, name, args in CALLS:
            result = await client.call_tool(name, args)
            body = (json.dumps(result.structured_content, indent=2) if result.structured_content
                    else result.content[0].text)
            lines += [f"## {label}: `{name}`\n", f"Request:\n```json\n{json.dumps(args, indent=2)}\n```\n",
                      f"Response (is_error={result.is_error}):\n```\n{body}\n```\n"]
            print(f"{label}: {name} -> is_error={result.is_error}")
    with open("demo_transcript.md", "w") as f:
        f.write("\n".join(lines))
    print("Saved demo_transcript.md")


if __name__ == "__main__":
    asyncio.run(main())
