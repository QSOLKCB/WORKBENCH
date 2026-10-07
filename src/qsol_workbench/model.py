"""The deliberately small workbench/1 capability contract."""
from dataclasses import dataclass
import hashlib
import json
import math


def json_loads(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"Non-finite JSON number: {value}")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("JSON number exceeds finite range")
        return number

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid, parse_float=finite_float)


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def field(name, kind="string", **options):
    return {"name": name, "type": kind, "label": name.replace("_", " ").title(), **options}


def validate(fields, supplied):
    if not isinstance(supplied, dict):
        raise ValueError("Parameters must be a JSON object")
    unknown = set(supplied) - {f["name"] for f in fields}
    if unknown:
        raise ValueError(f"Unknown parameters: {', '.join(sorted(unknown))}")
    result = {}
    for spec in fields:
        name = spec["name"]
        if name not in supplied:
            if "default" in spec:
                value = spec["default"]
            elif spec.get("required"):
                raise ValueError(f"{name} is required")
            else:
                continue
        else:
            value = supplied[name]
        kind = spec["type"]
        valid = {
            "string": isinstance(value, str),
            "integer": type(value) is int,
            "number": type(value) in (int, float),
            "boolean": type(value) is bool,
        }.get(kind, False)
        if not valid:
            raise ValueError(f"{name} must be {kind}")
        if kind in ("integer", "number"):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            if "minimum" in spec and value < spec["minimum"]:
                raise ValueError(f"{name} is below {spec['minimum']}")
            if "maximum" in spec and value > spec["maximum"]:
                raise ValueError(f"{name} exceeds {spec['maximum']}")
        if kind == "string" and len(value) > spec.get("max_length", 32768):
            raise ValueError(f"{name} is too long")
        if spec.get("required") and value == "":
            raise ValueError(f"{name} cannot be empty")
        if "choices" in spec and value not in spec["choices"]:
            raise ValueError(f"{name} must be one of {spec['choices']}")
        result[name] = value
    return result


@dataclass
class Plan:
    argv: list[str]
    cwd: str | None = None
    stdin: str | None = None
    result_kind: str = "json"
    expected_operation: str | None = None
    expected_schema: str | None = None
    success_field: str | None = None
    validate_result: object | None = None


@dataclass
class Action:
    id: str
    title: str
    description: str
    fields: list
    backend: dict
    build: object
    effect: str = "local-compute"
    output: dict | None = None

    def public(self):
        spec = {"id": self.id, "title": self.title, "description": self.description,
                "fields": self.fields, "backend": self.backend, "effect": self.effect}
        if self.output is not None:
            spec["output"] = self.output
        return {**spec, "schema_sha256": digest(spec)}
