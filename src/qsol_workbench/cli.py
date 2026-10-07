import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .model import json_loads
from .runtime import Runtime


def main(argv=None):
    parser = argparse.ArgumentParser(description="QSOL Workbench — discover, run, inspect")
    parser.add_argument("--version", action="version", version=f"qsol-workbench {__version__}")
    parser.add_argument("--config", help="Local JSON adapter configuration")
    parser.add_argument("--store", default=".workbench/runs", help="Run record directory")
    parser.add_argument("--timeout", type=float, default=120, help="Maximum execution seconds")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("discover", help="Print connection status and current capabilities")
    run = commands.add_parser("run", help="Run a discovered action and print its final record")
    run.add_argument("action")
    group = run.add_mutually_exclusive_group()
    group.add_argument("--params", default="{}", help="JSON input object")
    group.add_argument("--params-file", help="JSON input file; use - to read stdin")
    commands.add_parser("history", help="List local run records")
    show = commands.add_parser("show", help="Read a run record")
    show.add_argument("id")
    commands.add_parser("tui", help="Open the curses terminal interface")
    web = commands.add_parser("web", help="Open the loopback browser server")
    web.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    runtime = None
    try:
        if not 0 < args.timeout <= 86400:
            raise ValueError("Timeout must be between 0 and 86400 seconds")
        config = json_loads(Path(args.config).read_text()) if args.config else {}
        if not isinstance(config, dict):
            raise ValueError("Configuration must be an object")
        runtime = Runtime(config, args.store, args.timeout)
        if args.command == "discover":
            result = runtime.manifest()
        elif args.command == "history":
            result = runtime.history()
        elif args.command == "show":
            result = runtime.get(args.id)
        elif args.command == "run":
            text = args.params
            if args.params_file:
                text = sys.stdin.read(65537) if args.params_file == "-" else Path(args.params_file).read_text()
            if len(text.encode()) > 65536:
                raise ValueError("Parameters exceed 65536 bytes")
            record = runtime.start(args.action, json_loads(text))
            try:
                result = runtime.wait(record["id"])
            except KeyboardInterrupt:
                runtime.cancel(record["id"])
                result = runtime.wait(record["id"])
            print(json.dumps(result, indent=2, ensure_ascii=True))
            return 0 if result["status"] == "succeeded" and not result.get("persistence_error") else 1
        elif args.command == "web":
            from .web import serve
            serve(runtime, args.port)
            return 0
        else:
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                raise ValueError("TUI requires an interactive terminal; use discover/run/web otherwise")
            from .tui import launch
            launch(runtime)
            return 0
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, ImportError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    finally:
        if runtime:
            runtime.close()
