"""Small curses presentation. All discovery and execution live in Runtime."""
import curses
import json


def clean(text):
    return "".join(c if c.isprintable() else " " for c in str(text))


def launch(runtime):
    def app(screen):
        curses.curs_set(0)
        screen.timeout(150)
        selected, field_index, run_id, notice = 0, 0, None, ""
        manifest = runtime.manifest()
        params = {}

        def write(y, x, value, style=0):
            height, width = screen.getmaxyx()
            if 0 <= y < height - 1 and 0 <= x < width - 1:
                try:
                    screen.addnstr(y, x, clean(value), max(0, width - x - 2), style)
                except curses.error:
                    pass

        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            actions = manifest["actions"]
            selected = min(selected, max(0, len(actions) - 1))
            action = actions[selected] if actions else None
            write(0, 1, "QSOL WORKBENCH", curses.A_BOLD)
            write(1, 1, "↑↓ select  Tab field  e edit  r run  c stop  h history  f refresh  q quit")
            write(2, 1, "Connections: " + "  ".join(c["id"] + ":" + c["status"] for c in manifest["connections"]))
            split = max(25, width // 3)
            for i, entry in enumerate(actions):
                write(4 + i, 1, ("> " if i == selected else "  ") + entry["title"][:split-4],
                      curses.A_REVERSE if i == selected else 0)
            if action:
                values = params.setdefault(action["id"], {f["name"]: f["default"] for f in action["fields"] if "default" in f})
                write(4, split, action["id"])
                for i, spec in enumerate(action["fields"]):
                    value = values.get(spec["name"], "<required>" if spec.get("required") else "<omitted>")
                    write(6 + i, split, f"{'>' if i == field_index else ' '} {spec['name']}: {value}")
            top = max(12, 8 + (len(action["fields"]) if action else 0))
            if run_id:
                record = runtime.get(run_id)
                write(top, 1, f"Run {run_id[:12]}  {record['status']}", curses.A_BOLD)
                output = record["stderr"] + "\n" + record["stdout"]
                if record.get("error"):
                    output += "\n" + record["error"]
                for i, line in enumerate(output.splitlines()[-max(1, height-top-4):]):
                    write(top + 1 + i, 1, line)
            write(height - 2, 1, notice)
            screen.refresh()
            key = screen.getch()
            try:
                if key == ord("q"):
                    return
                if key in (curses.KEY_DOWN, ord("j")) and actions:
                    selected = (selected + 1) % len(actions)
                    field_index = 0
                elif key in (curses.KEY_UP, ord("k")) and actions:
                    selected = (selected - 1) % len(actions)
                    field_index = 0
                elif key == 9 and action and action["fields"]:
                    field_index = (field_index + 1) % len(action["fields"])
                elif key == ord("e") and action and action["fields"]:
                    spec = action["fields"][field_index]
                    screen.move(height - 2, 0)
                    screen.clrtoeol()
                    write(height - 2, 1, f"{spec['name']} ({spec['type']}): ")
                    curses.echo()
                    curses.curs_set(1)
                    screen.timeout(-1)
                    try:
                        raw = screen.getstr(height - 1, 1, max(1, min(width - 3, 4096))).decode("utf-8")
                    finally:
                        screen.timeout(150)
                        curses.noecho()
                        curses.curs_set(0)
                    values[spec["name"]] = raw if spec["type"] == "string" else json.loads(raw)
                elif key == ord("r") and action:
                    run_id = runtime.start(action["id"], values, action["schema_sha256"])["id"]
                    notice = "Run started; q cancels active work before exiting"
                elif key == ord("c") and run_id:
                    runtime.cancel(run_id)
                elif key == ord("h"):
                    recent = runtime.history()
                    if recent:
                        run_id = recent[0]["id"]
                elif key == ord("f"):
                    manifest = runtime.refresh()
                    params.clear()
                    field_index = 0
                    notice = "Capabilities refreshed"
            except (ValueError, OSError, KeyError) as error:
                notice = str(error)

    curses.wrapper(app)
