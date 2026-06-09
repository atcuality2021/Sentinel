"""Sentinel CLI.

    python -m sentinel "Stripe" --mode competitor
    python -m sentinel "Acme Corp" --mode client --vertical "BFSI"
    python -m sentinel "Stripe" --writer markdown --out artifacts_out

Loads .env if present (GOOGLE_API_KEY etc.).
"""

from __future__ import annotations

import argparse
import sys

from sentinel.artifacts.writer import get_writer


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    _load_env()
    parser = argparse.ArgumentParser(prog="sentinel", description="Sovereign Intelligence Agent")
    parser.add_argument("target", help="Competitor name (competitor mode) or account name (client mode)")
    parser.add_argument("--mode", choices=["competitor", "client"], default="competitor")
    parser.add_argument("--vertical", default=None, help="Optional industry context")
    parser.add_argument("--writer", choices=["markdown", "gdoc", "crm"], default="markdown")
    parser.add_argument("--out", default="artifacts_out", help="Output dir for markdown writer")
    parser.add_argument(
        "--backend",
        choices=["gemini", "vllm"],
        default=None,
        help="Reasoning backend. Default: SENTINEL_LLM_BACKEND env (else gemini). "
        "'vllm' runs synthesis on a local Gemma server.",
    )
    args = parser.parse_args(argv)

    # Import after env load so backend selection sees the env.
    from sentinel.agent.orchestrator import run

    writer = get_writer("markdown", out_dir=args.out) if args.writer == "markdown" else get_writer(args.writer)

    print(f"▶ Sentinel · mode={args.mode} · target={args.target!r}", file=sys.stderr)
    result = run(
        args.target, args.mode, vertical_context=args.vertical, writer=writer, backend=args.backend
    )

    print("\n── run trace ──", file=sys.stderr)
    for line in result.trace:
        print(f"  {line}", file=sys.stderr)

    print(f"\n✓ artifact ({args.mode}) → {result.write.reference}  [backend={result.backend}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
