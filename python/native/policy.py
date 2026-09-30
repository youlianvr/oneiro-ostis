"""Trusted capability metadata. Neither a prompt nor SOUL can grant permissions."""
from __future__ import annotations

from dataclasses import dataclass

from native.memory import ROLES

EFFECTS = frozenset({"read", "note", "coordinate", "workspace_write", "web_read",
                     "configure", "delete", "database", "sandbox", "install",
                     "publish", "send", "upload", "autostart"})
SENSITIVE = frozenset({"configure", "delete", "database", "sandbox", "install",
                       "publish", "send", "upload"})
ROLE_EFFECTS = {
    "manager": {"read", "note", "coordinate", "web_read"},
    "researcher": {"read", "note", "web_read"},
    "executor": set(EFFECTS) - {"coordinate", "autostart"},
}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    properties: dict
    required: tuple[str, ...]
    roles: tuple[str, ...]
    effect: str
    handler: object

    def __post_init__(self):
        if self.effect not in EFFECTS or not self.roles or set(self.roles) - set(ROLES):
            raise ValueError("Tool needs reviewed effect and role metadata")
        if any(self.effect not in ROLE_EFFECTS[role] for role in self.roles):
            raise ValueError("Tool violates permanent role boundaries")

    def schema(self):
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "properties": self.properties,
                           "required": list(self.required), "additionalProperties": False}}}

    def validate(self, args):
        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be an object")
        if set(args) - set(self.properties) or set(self.required) - set(args):
            raise ValueError("Unexpected or missing tool arguments")
        types = {"string": str, "integer": int, "boolean": bool, "object": dict, "array": list}
        for name, value in args.items():
            expected = self.properties[name].get("type")
            if expected in types and (not isinstance(value, types[expected])
                                     or expected == "integer" and isinstance(value, bool)):
                raise ValueError(f"Invalid type for {name}")
            choices = self.properties[name].get("enum")
            if choices and value not in choices:
                raise ValueError(f"Invalid value for {name}")


class Policy:
    def __init__(self, settings):
        self.settings = settings

    def check(self, tool: Tool, role: str, args: dict, *, approved=False, trusted_url=False):
        if role not in tool.roles or tool.effect not in ROLE_EFFECTS.get(role, set()):
            return "deny", "Permanent role boundary"
        tool.validate(args)
        if tool.effect == "autostart":
            return "deny", "Autostart is disabled"
        if tool.effect == "upload" and not self.settings["virustotal_uploads"]:
            return "deny", "VirusTotal uploads are disabled"
        if approved:
            return "allow", "Owner approved this exact action"
        if tool.effect == "upload" and self.settings["virustotal_uploads"]:
            return "allow", "Owner enabled the VirusTotal file-upload exception"
        mode = self.settings["permission_mode"]
        if tool.effect in SENSITIVE:
            return "ask", "Separate button confirmation required for this effect"
        if tool.effect == "web_read":
            if not self.settings["internet_enabled"]:
                return "deny", "Internet access is disabled"
            if not trusted_url:
                return "ask", "Approve the exact outbound URL; no local information may leak in a request"
        if mode == "review" and tool.effect == "workspace_write":
            return "ask", "Review mode requires confirmation of project edits"
        return "allow", "Within the configured local permissions"
