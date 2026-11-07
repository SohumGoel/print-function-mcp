# print-function MCP server

Function-aware checks for failed or imperfect FDM prints (CMU 24-679 Project 2). The tools answer the question operators actually face: **can this part still do its job, and is it worth finishing?** Built with the official MCP Python SDK (`mcp` 2.3, `MCPServer`).

## Setup

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12+ installed automatically). MCP Inspector also needs Node.js.

```bash
cd print-mcp
uv sync                    # install dependencies
uv run pytest -q           # hand-calculation checks
uv run mcp dev server.py   # MCP Inspector in the browser
uv run demo_client.py      # scripted stdio client → demo_transcript.md
uv run bench_tools.py      # tool latency over MCP (50 calls each)
```

Agent test: 10 plain-English requests; scores tool choice and arguments (needs `transformers`, `accelerate` and a GPU, e.g. Colab):
```bash
python eval_agent.py --backend transformers --model Qwen/Qwen3-4B-Instruct-2507   # → eval_report.md
python eval_agent.py --backend openai --base-url <OpenAI-compatible URL> --model <name>
```

Connect from Claude Code: `claude mcp add print-function -- uv --directory /absolute/path/to/print-function-mcp run server.py`. Other clients: see `mcp.example.json` (no credentials needed).

## Tools

Units: mm (x, y measured from the part's datum frame), hours, grams, USD.

| Tool | Purpose | Typed inputs (valid range) | Structured result |
|---|---|---|---|
| `feature_position_check` | GD&T true position of a hole axis, with MMC bonus | nominal and measured x, y (−500 to 500 mm); position tolerance (0.01–5 mm); optional MMC and measured hole size (0.5–50 mm) | radial offset, deviation (zone diameter), bonus, allowed tolerance, margin, in-tolerance flag |
| `fastener_fit_check` | Whether a bolt passes a printed hole vs ISO 273 | fastener (M3–M12), measured hole (0.5–50 mm), fit class (fine/medium/coarse) | ISO 273 holes, shortfall, bolt passes, floating position tolerance T = H − F, verdict |
| `failure_waste` | What an abandoned print wasted | part mass (1–5,000 g), print time (0.1–200 h), progress (0–100%), filament $/kg, printer W, $/kWh, machine $/h | wasted g, h, kWh, USD; full print cost |
| `layer_shift_impact` | Which features a layer shift moves or splits relative to the datums | shift dx, dy (±50 mm), shift height (0–500 mm), features (name, z range, position tolerance, optional hole size and bolt) | per feature: status, deviation, step, clear through-diameter, bolt passes, functional; overall verdict |
| `continue_or_scrap` | Expected cost and hours to a usable part: finish vs scrap and reprint | progress, print time, mass, probability usable if continued (0–1), reprint success (0.05–1), cost inputs | expected cost and hours for both options, break-even probability, cheaper option |

Every result includes a `scope` field listing its assumptions.

## Invalid-input behavior

Invalid input never returns a number; the server replies with `isError: true` and a readable message.
1. **Schema level:** ranges, enums and types are in each tool's JSON schema, so values like `fastener: "M7"` are rejected before any calculation runs.
2. **Calculation level:** checks the schema can't express, such as a feature whose top is below its bottom, raise `ToolError` with the reason.

## Client and server responsibilities

| Server (this repo) | Client (Inspector, Claude, Pi or another agent) |
|---|---|
| Publishes each tool's name, description, input schema and output schema | Decides which tool fits the request and fills in the arguments |
| Validates every input (types, units, ranges, enums) and rejects bad values with an error | Converts the user's units and wording into the tool's inputs (e.g. inches → mm) |
| Runs the deterministic calculation and returns a structured result with its `scope` | Explains the result, combines tools (e.g. shift check → continue-or-scrap) and asks a person when needed |
| Runs locally over stdio: no network, no part data leaves the machine | Owns the conversation, memory and any action on the printer |

The server never measures the part, controls the printer or makes the final call.

## What a person should verify before acting

- **Inputs:** measured positions and hole sizes are taken from the right datums, in mm, by a trustworthy method (calipers, calibrated camera).
- **The right number:** position is judged on the zone diameter (`position_deviation_dia_mm`), not the radial offset.
- **Strength:** every tool checks geometry or cost only. A part that passes can still be weak (layer adhesion, a shifted load path), so load-bearing parts need a physical check.
- **Judgment inputs:** `p_usable_if_continued` and the cost defaults are assumptions; replace them with real values before trusting `continue_or_scrap`.

## How the tools connect to user research

Interview evidence (anonymized, HW5):
- Unattended overnight printing is the main pain, and a compromised part is fine if it still works (P2) → `layer_shift_impact`, `feature_position_check`, `fastener_fit_check` judge function, not looks.
- Geometry alone doesn't prove function; material behavior matters (P3) → every result states "geometry only" in its `scope`, and strength is listed as a human check.
- Some organizations keep printers off the cloud for IP reasons (P1) → the server runs fully locally.
- Catch failures early rather than after the fact (P1) → `continue_or_scrap` puts numbers on the keep-going decision mid-print; `failure_waste` shows what a late discovery costs.

## Files

`print_tools.py` (calculations) · `server.py` (MCP tools, schemas, result models) · `test_tools.py` · `demo_client.py` + `demo_transcript.md` · `bench_tools.py` · `eval_agent.py` + `eval_report_qwen3-4b.md` · `mcp.example.json`

## Sources

ASME Y14.5 (position tolerance, MMC bonus; floating fastener T = H − F). ISO 273 clearance holes. Song & Telenko (2017) on failure waste in FDM shops. MCP Python SDK documentation.
