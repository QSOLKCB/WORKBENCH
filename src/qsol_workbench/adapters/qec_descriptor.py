"""Validate QEC's public scalar descriptor; no parser introspection here."""
from copy import deepcopy
import math
import re

from ..model import Action, Plan, digest, validate

COMMANDS = {
    "qec.ququart.benchmark": ("qec.benchmark.ququart_battery.cli", "qec.ququart-fer-battery.v170.1.1", "artifact-manifest"),
    "qec.ququart.validate": ("qec.benchmark.ququart_battery.validate_cli", "qec.ququart-report-claim-validation.v1", "validation-receipt"),
    "qec.qutrit.benchmark": ("qec.benchmark.qutrit_battery.cli", "qec.qutrit-decoder-benchmark.v1", "artifact-manifest"),
}
FIELD_KEYS = {"name", "flag", "label", "type", "required", "help", "default", "choices", "minimum", "maximum",
              "max_length", "multiline", "path_role", "path_base"}


def compatible(condition, message):
    if not condition:
        raise ValueError("QEC descriptor compatibility error: " + message)


def scalar_fields(fields):
    compatible(isinstance(fields, list) and len(fields) <= 128, "fields must be a bounded scalar list")
    names, flags = set(), set()
    for field in fields:
        compatible(isinstance(field, dict) and not set(field) - FIELD_KEYS, "unsupported/custom input structure")
        name, flag, kind = field.get("name"), field.get("flag"), field.get("type")
        compatible(isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name), "invalid field name")
        compatible(isinstance(flag, str) and re.fullmatch(r"--[A-Za-z][A-Za-z0-9-]*", flag) and flag != "--help", "invalid scalar flag")
        compatible(name not in names and flag not in flags, "duplicate field or flag")
        names.add(name); flags.add(flag)
        compatible(kind in ("string", "integer", "number", "boolean"), "unsupported input type: " + str(kind))
        compatible(isinstance(field.get("label"), str) and type(field.get("required", False)) is bool, "invalid label/requiredness")
        compatible(isinstance(field.get("help", ""), str) and type(field.get("multiline", False)) is bool, "invalid presentation hints")
        if "path_role" in field or "path_base" in field:
            compatible(kind == "string" and field.get("path_base") == "cwd" and
                       field.get("path_role") in ("read-file", "write-file", "read-directory", "write-directory"), "unsupported path semantics")
        if "max_length" in field:
            compatible(kind == "string" and type(field["max_length"]) is int and field["max_length"] >= 0, "invalid string bound")
        for bound in ("minimum", "maximum"):
            if bound in field:
                value = field[bound]
                compatible(kind in ("integer", "number") and type(value) in (int, float) and
                           (not isinstance(value, float) or math.isfinite(value)), "invalid numeric bound")
        compatible("minimum" not in field or "maximum" not in field or field["minimum"] <= field["maximum"], "inverted numeric bounds")
        if "default" in field:
            validate([field], {name: field["default"]})
        if "choices" in field:
            compatible(isinstance(field["choices"], list) and bool(field["choices"]), "invalid choices")
            for choice in field["choices"]:
                validate([field], {name: choice})
    return deepcopy(fields)


def actions_from_descriptor(discovery, python, cwd):
    descriptor = discovery["descriptor"]
    compatible(descriptor.get("protocol") == "qec-capabilities/1", "unsupported protocol")
    actions = descriptor.get("actions")
    compatible(isinstance(actions, list) and bool(actions) and len(actions) <= len(COMMANDS), "invalid action list")
    found, ids = [], set()
    for action in actions:
        compatible(isinstance(action, dict) and not set(action) - {"id", "module", "title", "description", "fields", "effect", "output"}, "unsupported action structure")
        action_id = action.get("id")
        compatible(isinstance(action_id, str) and action_id in COMMANDS and action_id not in ids, "unknown or duplicate action")
        ids.add(action_id)
        module, schema, view = COMMANDS[action_id]
        compatible(action.get("module") == module, "unreviewed command entry point")
        compatible(isinstance(action.get("title"), str) and isinstance(action.get("description"), str), "invalid action text")
        compatible(action.get("effect") in ("read", "writes-artifacts", "local-compute"), "unsupported effect")
        fields = scalar_fields(action.get("fields"))
        output = action.get("output")
        compatible(isinstance(output, dict) and not set(output) - {"format", "schema", "view", "directory_field", "success_field"}, "unsupported output structure")
        compatible(output.get("format") == "json" and output.get("schema") == schema and output.get("view") == view, "unsupported output contract")
        if view == "artifact-manifest":
            compatible(any(field["name"] == output.get("directory_field") and field.get("path_role") == "write-directory" for field in fields), "missing artifact directory contract")
            compatible("success_field" not in output, "unexpected artifact success field")
        else:
            compatible(output.get("success_field") == "passed", "validation receipt must declare its success field")
        identity = {**discovery["backend"], **discovery["modules"][module], "cwd": cwd,
                    "descriptor_sha256": digest(descriptor), "implementation_modules": discovery["modules"]}
        output = deepcopy(output)

        def build(parameters, fields=fields, module=module, output=output):
            argv = [python, "-m", module]
            for field in fields:
                name = field["name"]
                if name in parameters:
                    value = parameters[name]
                    text = ("true" if value else "false") if field["type"] == "boolean" else str(value)
                    argv.append(field["flag"] + "=" + text)
            return Plan(argv, cwd=cwd, expected_schema=output["schema"], success_field=output.get("success_field"))

        found.append(Action(action_id, action["title"], action["description"], fields, identity, build, action["effect"], output))
    return found
