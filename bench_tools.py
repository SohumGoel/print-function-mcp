"""Tool latency over a real stdio MCP connection: 50 calls per tool. Run: uv run bench_tools.py"""

import asyncio
import statistics
import sys
import time

from mcp import Client, StdioServerParameters

from demo_client import CALLS

N = 50


async def main():
    async with Client(StdioServerParameters(command=sys.executable, args=["server.py"])) as client:
        print(f"{'tool':26} {'mean ms':>8} {'p95 ms':>8}")
        for label, name, args in CALLS:
            if label.startswith("Invalid"):
                continue
            times = []
            for _ in range(N):
                t = time.perf_counter()
                await client.call_tool(name, args)
                times.append((time.perf_counter() - t) * 1000)
            p95 = statistics.quantiles(times, n=20)[18]
            print(f"{name:26} {statistics.mean(times):8.2f} {p95:8.2f}")


if __name__ == "__main__":
    asyncio.run(main())
