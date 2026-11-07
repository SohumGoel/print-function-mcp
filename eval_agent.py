"""Agent evaluation: does an LLM pick the right MCP tool with the right arguments?

The model sees only the MCP tool list (names, descriptions, JSON schemas), exactly as an MCP client
would pass it. Each case is a plain-English request with the expected tool(s) and key arguments.
Two backends:
    python eval_agent.py --backend transformers --model Qwen/Qwen3-4B-Instruct-2507   # local weights (Colab GPU)
    python eval_agent.py --backend openai --base-url http://localhost:11434/v1 --model qwen3:4b
Writes eval_report.md and eval_results.json.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time

from mcp import Client, StdioServerParameters

SYSTEM = (
    "You help makerspace operators decide what to do with imperfect or failed FDM prints. "
    "Use the tools for every number; never calculate yourself. Convert units to the tool's units "
    "first (1 in = 25.4 mm). If a tool returns an error, say what was wrong instead of guessing. "
    "If no tool fits the question, answer briefly without calling one. Finish with 1-3 sentences."
)

# (request, expected tools in order, key argument checks for the first expected call)
CASES = [
    ("Hole A should sit at x=20, y=15 mm from the datums. The camera measured x=20.12, y=14.91. "
     "Position tolerance is 0.2 mm at MMC, the hole's MMC size is 3.4 mm and it measured 3.55 mm. In tolerance?",
     ["feature_position_check"],
     {"nominal_x_mm": 20, "nominal_y_mm": 15, "measured_x_mm": 20.12, "measured_y_mm": 14.91,
      "position_tol_mm": 0.2, "hole_mmc_dia_mm": 3.4, "measured_hole_dia_mm": 3.55}),
    ("A printed hole measured 3.25 mm. Will an M3 bolt go through, and how does that compare with a normal "
     "medium clearance hole?",
     ["fastener_fit_check"], {"fastener": "M3", "measured_hole_dia_mm": 3.25}),
    ("The hole measured 0.134 inches across. Does an M3 bolt pass?",
     ["fastener_fit_check"], {"fastener": "M3", "measured_hole_dia_mm": 3.40}),
    ("Our 85 g, 6-hour bracket print failed at 70%. How much did we waste?",
     ["failure_waste"], {"part_mass_g": 85, "total_print_time_h": 6, "progress_pct": 70}),
    ("A 240 g, 14 h fixture died at 35%. Filament costs $25/kg, the printer draws 150 W and power is "
     "$0.18/kWh. What did the failure cost?",
     ["failure_waste"], {"part_mass_g": 240, "total_print_time_h": 14, "progress_pct": 35,
                         "filament_cost_per_kg": 25, "printer_power_w": 150, "electricity_cost_per_kwh": 0.18}),
    ("Layer shift: 0.4 mm in x and 0.3 mm in y, starting at 10 mm height. Features: base hole from z 0 to 4 mm "
     "with 0.3 mm position tolerance, and motor hole from z 12 to 18 mm with 0.3 mm tolerance. Still functional?",
     ["layer_shift_impact"], {"shift_dx_mm": 0.4, "shift_dy_mm": 0.3, "shift_height_mm": 10}),
    ("We're 60% through a 6 h, 85 g print and I'd say there's a 70% chance the part is still usable. "
     "Keep going or scrap it?",
     ["continue_or_scrap"], {"progress_pct": 60, "total_print_time_h": 6, "part_mass_g": 85,
                             "p_usable_if_continued": 0.7}),
    ("A 0.5 mm layer shift in x happened at 10 mm on a 6 h, 85 g bracket that's 60% done. The motor hole runs "
     "from z 12 to 18 mm with 0.3 mm position tolerance. Should we keep printing?",
     ["layer_shift_impact", "continue_or_scrap"], {"shift_dx_mm": 0.5, "shift_height_mm": 10}),
    ("Will an M7 bolt fit through a 7.5 mm printed hole?", ["fastener_fit_check|none"], {}),
    ("Which filament brand is the best for brackets?", ["none"], {}),
]


def close(a, b):
    if isinstance(b, (int, float)) and not isinstance(b, bool):
        return isinstance(a, (int, float)) and abs(a - b) <= max(0.02, 0.01 * abs(b))
    return str(a).lower() == str(b).lower()


def to_openai(tool):
    return {"type": "function", "function": {"name": tool.name, "description": tool.description or "",
                                             "parameters": tool.input_schema}}


class OpenAIChat:
    """Any OpenAI-compatible server (Ollama, vLLM, hosted APIs)."""

    def __init__(self, model, base_url, api_key):
        from openai import OpenAI
        self.client, self.model = OpenAI(base_url=base_url, api_key=api_key), model

    def chat(self, messages, tools):
        resp = self.client.chat.completions.create(model=self.model, messages=messages, tools=tools, temperature=0)
        msg = resp.choices[0].message
        calls = [{"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments or "{}"}
                 for tc in msg.tool_calls or []]
        return msg.content or "", calls, resp.usage.total_tokens if resp.usage else 0


class TransformersChat:
    """Local Hugging Face weights, as in HW4. Qwen chat templates emit <tool_call>{json}</tool_call>."""

    def __init__(self, model_id, max_new_tokens=512):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        cuda = torch.cuda.is_available()
        dtype = (torch.bfloat16 if cuda and torch.cuda.is_bf16_supported() else torch.float16) if cuda else torch.float32
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(model_id, dtype=dtype, device_map="auto").eval()
        for flag in ("temperature", "top_p", "top_k"):      # greedy decoding, as in HW4
            setattr(self.model.generation_config, flag, None)
        self.max_new_tokens = max_new_tokens

    def chat(self, messages, tools):
        inputs = self.tok.apply_chat_template(messages, tools=tools, add_generation_prompt=True,
                                              return_tensors="pt", return_dict=True).to(self.model.device)
        with self.torch.inference_mode():
            out = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False,
                                      pad_token_id=self.tok.eos_token_id)
        new = out[0][inputs["input_ids"].shape[-1]:]
        text = self.tok.decode(new, skip_special_tokens=True)
        calls = []
        for i, block in enumerate(re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.S)):
            try:
                obj = json.loads(block)
                calls.append({"id": f"call_{i}", "name": obj.get("name", ""),
                              "arguments": json.dumps(obj.get("arguments", {}))})
            except json.JSONDecodeError:
                calls.append({"id": f"call_{i}", "name": "_unparsed", "arguments": block})
        content = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.S).strip()
        return content, calls, int(inputs["input_ids"].shape[-1] + len(new))


async def run_case(llm, client, tools, request, max_turns=5):
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": request}]
    calls, tokens, t0 = [], 0, time.time()
    for _ in range(max_turns):
        content, tool_calls, used = llm.chat(messages, tools)
        tokens += used
        if not tool_calls:
            return {"calls": calls, "answer": content, "tokens": tokens, "seconds": time.time() - t0}
        messages.append({"role": "assistant", "content": content,
                         "tool_calls": [{"id": c["id"], "type": "function",
                                         "function": {"name": c["name"], "arguments": c["arguments"]}}
                                        for c in tool_calls]})
        for c in tool_calls:
            try:
                args = json.loads(c["arguments"])
            except json.JSONDecodeError:
                args = {"_unparsed": c["arguments"]}
            t = time.time()
            result = await client.call_tool(c["name"], args)
            text = (json.dumps(result.structured_content) if result.structured_content
                    else result.content[0].text if result.content else "")
            calls.append({"tool": c["name"], "args": args, "is_error": result.is_error,
                          "tool_ms": round((time.time() - t) * 1000, 1)})
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": text})
    return {"calls": calls, "answer": "(stopped: turn limit)", "tokens": tokens, "seconds": time.time() - t0}


def score(expected, checks, out):
    used = [c["tool"] for c in out["calls"]]
    if expected == ["none"]:
        return not used, None
    if expected == ["fastener_fit_check|none"]:          # unsupported input: refuse or surface the error
        return (not used) or any(c["is_error"] for c in out["calls"]), None
    tool_ok = [t for t in used if t in expected][:len(expected)] == expected and used[0] == expected[0]
    first = next((c for c in out["calls"] if c["tool"] == expected[0]), None)
    bad = [k for k, v in checks.items() if not first or not close(first["args"].get(k), v)]
    return tool_ok, bad


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["transformers", "openai"], default="transformers")
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", "not-needed"))
    ap.add_argument("--cases", default="", help="comma-separated case numbers to run, e.g. 1,3")
    a = ap.parse_args()
    llm = (TransformersChat(a.model) if a.backend == "transformers"
           else OpenAIChat(a.model, a.base_url, a.api_key))
    wanted = {int(x) for x in a.cases.split(",") if x.strip()}
    rows = []
    async with Client(StdioServerParameters(command=sys.executable, args=["server.py"])) as client:
        tools = [to_openai(t) for t in (await client.list_tools()).tools]
        for i, (request, expected, checks) in enumerate(CASES, 1):
            if wanted and i not in wanted:
                continue
            out = await run_case(llm, client, tools, request)
            tool_ok, bad_args = score(expected, checks, out)
            rows.append({"case": i, "request": request, "expected": expected, **out,
                         "tool_ok": tool_ok, "bad_args": bad_args})
            print(f"case {i:2d}: tools={[c['tool'] for c in out['calls']]} tool_ok={tool_ok} "
                  f"bad_args={bad_args} {out['seconds']:.1f}s")

    n = len(rows)
    arg_rows = [r for r in rows if r["bad_args"] is not None]
    tool_ms = [c["tool_ms"] for r in rows for c in r["calls"]]
    summary = {
        "model": a.model,
        "tool_selection": f"{sum(r['tool_ok'] for r in rows)}/{n}",
        "arguments_exact": f"{sum(not r['bad_args'] for r in arg_rows)}/{len(arg_rows)}",
        "mean_tool_calls": round(sum(len(r['calls']) for r in rows) / n, 2),
        "mean_seconds_per_request": round(sum(r['seconds'] for r in rows) / n, 1),
        "mean_tool_ms": round(sum(tool_ms) / max(len(tool_ms), 1), 1),
        "total_tokens": sum(r["tokens"] for r in rows),
    }
    lines = [f"# Agent evaluation: {a.model}\n", "| Metric | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in summary.items()]
    lines += ["", "| # | Expected | Called | Tool OK | Wrong args | Time (s) |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['case']} | {', '.join(r['expected'])} | {', '.join(c['tool'] for c in r['calls']) or 'none'} "
                     f"| {'✅' if r['tool_ok'] else '❌'} | {', '.join(r['bad_args'] or []) or '-'} | {r['seconds']:.1f} |")
    lines += ["", "## Answers"] + [f"**{r['case']}.** {r['answer'].strip()}\n" for r in rows]
    open("eval_report.md", "w").write("\n".join(lines))
    json.dump({"summary": summary, "cases": rows}, open("eval_results.json", "w"), indent=2, default=str)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
