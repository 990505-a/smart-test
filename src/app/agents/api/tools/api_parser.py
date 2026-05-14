"""API Parser — parses OpenAPI Swagger specifications.

This is a programmed agent that fetches and parses API specifications in
OpenAPI/Swagger JSON format, resolving $ref references and extracting
structured operation details (paths, methods, parameters, responses, schemas).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import requests
import yaml


def _resolve_ref(ref: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Resolve a JSON Schema $ref pointer within the spec document.

    Args:
        ref: The $ref value (e.g. "#/components/schemas/Pet").
        spec: The full OpenAPI specification document.

    Returns:
        The resolved schema node.
    """
    if not ref.startswith("#/"):
        msg = f"External $ref not supported: {ref}"
        raise ValueError(msg)
    parts = ref[2:].split("/")
    node: Any = spec
    for part in parts:
        node = node[part]
    return node


def _resolve_all_refs(obj: Any, spec: dict[str, Any]) -> Any:
    """Recursively resolve all $ref references in an object.

    Args:
        obj: Any JSON-like object potentially containing $ref.
        spec: The full OpenAPI specification document.

    Returns:
        The object with all $ref resolved inline.
    """
    if isinstance(obj, dict):
        if "$ref" in obj and len(obj) == 1:
            return _resolve_all_refs(_resolve_ref(obj["$ref"], spec), spec)
        return {k: _resolve_all_refs(v, spec) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_all_refs(item, spec) for item in obj]
    return obj


def _load_spec(spec_url_or_path: str) -> dict[str, Any]:
    """Load an OpenAPI specification from a URL or local file path.

    Handles both JSON and YAML formats.

    Args:
        spec_url_or_path: URL or file path to the OpenAPI spec.

    Returns:
        Parsed specification dictionary.

    Raises:
        ValueError: If the spec cannot be loaded or parsed.
    """
    if spec_url_or_path.startswith(("http://", "https://")):
        resp = requests.get(spec_url_or_path, timeout=30)
        resp.raise_for_status()
        content = resp.text
    else:
        with open(spec_url_or_path, encoding="utf-8") as f:
            content = f.read()

    # Try JSON first, fall back to YAML
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return yaml.safe_load(content)


def parse_api_operations(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract all API operations from an OpenAPI specification.

    Each operation includes:
    - method: HTTP method (GET, POST, PUT, DELETE, PATCH)
    - path: API endpoint path
    - summary: Short description
    - description: Full description
    - operationId: Unique operation identifier
    - parameters: List of parameter definitions (resolved)
    - requestBody: Request body schema (resolved, if present)
    - responses: Response status codes and schemas (resolved)
    - tags: API tags

    Args:
        spec: Parsed OpenAPI specification dictionary.

    Returns:
        List of operation dictionaries.
    """
    operations: list[dict[str, Any]] = []
    paths = spec.get("paths", {})

    for path, path_item in paths.items():
        for method in ("get", "post", "put", "delete", "patch", "options", "head"):
            operation = path_item.get(method)
            if operation is None:
                continue

            # Resolve parameters
            parameters: list[dict[str, Any]] = []
            # Path-level parameters
            for param in path_item.get("parameters", []):
                parameters.append(_resolve_all_refs(param, spec))
            # Operation-level parameters (override path-level by name)
            op_params = {p["name"]: p for p in parameters}
            for param in operation.get("parameters", []):
                resolved = _resolve_all_refs(param, spec)
                op_params[resolved["name"]] = resolved
            resolved_params = list(op_params.values())

            # Resolve request body
            request_body = None
            if "requestBody" in operation:
                request_body = _resolve_all_refs(operation["requestBody"], spec)

            # Resolve responses
            responses: dict[str, Any] = {}
            for status_code, response in operation.get("responses", {}).items():
                responses[status_code] = _resolve_all_refs(response, spec)

            operations.append({
                "method": method.upper(),
                "path": path,
                "summary": operation.get("summary", ""),
                "description": operation.get("description", ""),
                "operationId": operation.get("operationId", f"{method}_{path}"),
                "parameters": resolved_params,
                "requestBody": request_body,
                "responses": responses,
                "tags": operation.get("tags", []),
            })

    return operations


def parse_api_spec(spec_url_or_path: str) -> dict[str, Any]:
    """Parse an OpenAPI specification into a structured representation.

    This is the main entry point for the API Parser agent.

    Args:
        spec_url_or_path: URL or file path to the OpenAPI specification.

    Returns:
        A dictionary containing:
        - info: API metadata (title, version, description)
        - servers: List of server URLs
        - operations: List of parsed API operations
        - schemas: Component schemas
        - security: Security schemes (if any)
    """
    spec = _load_spec(spec_url_or_path)

    info = spec.get("info", {})
    servers = spec.get("servers", [])
    operations = parse_api_operations(spec)

    # Extract component schemas
    schemas = {}
    components = spec.get("components", {})
    for schema_name, schema_def in components.get("schemas", {}).items():
        schemas[schema_name] = _resolve_all_refs(schema_def, spec)

    security = spec.get("security", [])
    security_schemes = components.get("securitySchemes", {})

    return {
        "title": info.get("title", "Untitled API"),
        "version": info.get("version", "unknown"),
        "description": info.get("description", ""),
        "servers": servers,
        "base_url": servers[0]["url"] if servers else "",
        "operations": operations,
        "schemas": schemas,
        "security": security,
        "security_schemes": security_schemes,
    }


def format_operations_for_prompt(
    parsed: dict[str, Any],
    operation_ids: list[str] | None = None,
) -> str:
    """Format parsed API operations as a string suitable for LLM prompts.

    Args:
        parsed: Output from parse_api_spec.
        operation_ids: Optional list of operationIds to include.
            If None, all operations are included.

    Returns:
        Formatted string describing the API operations.
    """
    lines: list[str] = [
        f"API Title: {parsed['title']}",
        f"API Version: {parsed['version']}",
        f"Base URL: {parsed['base_url']}",
        "",
    ]

    ops = parsed["operations"]
    if operation_ids:
        ops = [o for o in ops if o["operationId"] in operation_ids]

    for op in ops:
        lines.append(f"### {op['method']} {op['path']}")
        lines.append(f"OperationId: {op['operationId']}")
        if op["summary"]:
            lines.append(f"Summary: {op['summary']}")
        if op["description"]:
            lines.append(f"Description: {op['description']}")

        # Parameters
        if op["parameters"]:
            lines.append("Parameters:")
            for param in op["parameters"]:
                required = "required" if param.get("required") else "optional"
                schema_info = param.get("schema", {})
                ptype = schema_info.get("type", "string")
                enum = f" (values: {schema_info['enum']})" if "enum" in schema_info else ""
                lines.append(
                    f"  - {param['name']} ({param['in']}, {ptype}, {required}){enum}: "
                    f"{param.get('description', '')}"
                )

        # Request body
        if op.get("requestBody"):
            content = op["requestBody"].get("content", {})
            for content_type, media in content.items():
                schema = media.get("schema", {})
                ref = schema.get("$ref", schema.get("title", str(schema)))
                lines.append(f"RequestBody ({content_type}): {ref}")

        # Responses
        if op.get("responses"):
            lines.append("Responses:")
            for status, response in op["responses"].items():
                desc = response.get("description", "")
                lines.append(f"  {status}: {desc}")

        lines.append("")

    # Schemas
    if parsed.get("schemas"):
        lines.append("## Component Schemas")
        for name, schema in parsed["schemas"].items():
            lines.append(f"### {name}")
            props = schema.get("properties", {})
            if props:
                lines.append("Properties:")
                for prop_name, prop_schema in props.items():
                    ptype = prop_schema.get("type", "any")
                    lines.append(f"  - {prop_name}: {ptype} - {prop_schema.get('description', '')}")
            required = schema.get("required", [])
            if required:
                lines.append(f"Required: {', '.join(required)}")
            lines.append("")

    return "\n".join(lines)


# Re-export for tool registration: see tools/__init__.py
