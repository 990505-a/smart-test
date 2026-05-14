"""Tests for API Agent tools: api_parser, metrics, tools module."""
import json
import tempfile
from pathlib import Path

import pytest

from src.app.agents.api.tools.api_parser import (
    _resolve_all_refs,
    _resolve_ref,
    format_operations_for_prompt,
    parse_api_operations,
    parse_api_spec,
)
from src.app.agents.api.tools.metrics import check_script_syntax, compute_coverage


# =============================================================================
# TestApiParser
# =============================================================================


class TestApiParser:
    def test_parse_petstore_spec(self, tmp_path):
        """Parse a minimal OpenAPI 3.0 JSON spec and verify operations extracted."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Petstore", "version": "1.0.0"},
            "servers": [{"url": "https://petstore.example.com/v1"}],
            "paths": {
                "/pets": {
                    "get": {
                        "operationId": "listPets",
                        "summary": "List all pets",
                        "responses": {"200": {"description": "A list of pets"}},
                    },
                    "post": {
                        "operationId": "createPet",
                        "summary": "Create a pet",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Pet"}
                                }
                            }
                        },
                        "responses": {"201": {"description": "Pet created"}},
                    },
                }
            },
            "components": {
                "schemas": {
                    "Pet": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
                    }
                }
            },
        }
        spec_file = tmp_path / "petstore.json"
        spec_file.write_text(json.dumps(spec), encoding="utf-8")

        result = parse_api_spec(str(spec_file))
        assert result["title"] == "Petstore"
        assert result["version"] == "1.0.0"
        assert result["base_url"] == "https://petstore.example.com/v1"
        assert len(result["operations"]) == 2
        ops_by_id = {op["operationId"]: op for op in result["operations"]}
        assert "listPets" in ops_by_id
        assert ops_by_id["listPets"]["method"] == "GET"
        assert ops_by_id["createPet"]["method"] == "POST"
        # $ref should be resolved in requestBody
        create_op = ops_by_id["createPet"]
        schema = create_op["requestBody"]["content"]["application/json"]["schema"]
        assert "properties" in schema  # resolved from $ref

    def test_resolve_ref(self):
        """Resolve a simple $ref pointer."""
        spec = {
            "components": {
                "schemas": {
                    "Pet": {"type": "object", "properties": {"name": {"type": "string"}}}
                }
            }
        }
        result = _resolve_ref("#/components/schemas/Pet", spec)
        assert result["type"] == "object"
        assert "name" in result["properties"]

    def test_resolve_all_refs_recursive(self):
        """Nested $ref should be resolved recursively."""
        spec = {
            "components": {
                "schemas": {
                    "Pet": {
                        "type": "object",
                        "properties": {
                            "category": {"$ref": "#/components/schemas/Category"}
                        },
                    },
                    "Category": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}},
                    },
                }
            }
        }
        result = _resolve_all_refs({"$ref": "#/components/schemas/Pet"}, spec)
        assert result["properties"]["category"]["type"] == "object"

    def test_parse_yaml_spec(self, tmp_path):
        """Parse a YAML spec file successfully."""
        yaml_content = """
openapi: "3.0.0"
info:
  title: Test API
  version: "1.0"
paths:
  /items:
    get:
      operationId: listItems
      responses:
        "200":
          description: OK
"""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml_content, encoding="utf-8")

        result = parse_api_spec(str(spec_file))
        assert result["title"] == "Test API"
        assert len(result["operations"]) == 1
        assert result["operations"][0]["operationId"] == "listItems"

    def test_format_operations_for_prompt(self):
        """Formatted output contains method and path."""
        parsed = {
            "title": "Test API",
            "version": "1.0",
            "base_url": "https://api.example.com",
            "operations": [
                {
                    "method": "GET",
                    "path": "/items",
                    "operationId": "listItems",
                    "summary": "List items",
                    "description": "",
                    "parameters": [],
                    "responses": {"200": {"description": "OK"}},
                    "tags": [],
                }
            ],
        }
        output = format_operations_for_prompt(parsed)
        assert "GET" in output
        assert "/items" in output
        assert "listItems" in output


# =============================================================================
# TestCheckSyntax
# =============================================================================


class TestCheckSyntax:
    def test_valid_script(self):
        """Valid script with test() and balanced brackets returns valid=true."""
        script = """
import { test, expect } from '@playwright/test';

test('sample test', async ({ request }) => {
    const response = await request.get('/api/pets');
    expect(response.status()).toBe(200);
});
"""
        result = json.loads(check_script_syntax(script))
        assert result["valid"] is True
        assert result["error_count"] == 0

    def test_missing_test_block(self):
        """Script without test() or describe() reports an error."""
        script = "const x = 1;"
        result = json.loads(check_script_syntax(script))
        assert result["valid"] is False
        assert any("test()" in e or "describe()" in e for e in result["errors"])

    def test_mismatched_braces(self):
        """Script with unbalanced curly braces reports an error."""
        script = "test('ok', async () => {\n  const x = 1;\n}}"
        result = json.loads(check_script_syntax(script))
        assert result["valid"] is False
        assert any("braces" in e.lower() for e in result["errors"])

    def test_multiple_errors(self):
        """Script with both missing test and mismatched brackets."""
        script = "const x = {"
        result = json.loads(check_script_syntax(script))
        assert result["error_count"] >= 2


# =============================================================================
# TestComputeCoverage
# =============================================================================


class TestComputeCoverage:
    def _make_parsed_api(self):
        return json.dumps({
            "title": "Petstore",
            "operations": [
                {"operationId": "listPets"},
                {"operationId": "createPet"},
                {"operationId": "getPet"},
            ],
        })

    def test_scenario_coverage(self):
        """Scenario coverage calculated correctly from generated/accepted lists."""
        parsed = self._make_parsed_api()
        generated = json.dumps(["list pets", "create pet", "delete pet"])
        accepted = json.dumps(["list pets", "create pet"])
        result = json.loads(
            compute_coverage(parsed, generated_scenarios_json=generated, accepted_scenarios_json=accepted)
        )
        assert "scenario_coverage" in result
        assert result["scenario_coverage"]["accepted"] == 2
        assert result["scenario_coverage"]["generated"] == 3

    def test_operation_coverage(self):
        """Operation coverage counts tested/untested operations."""
        parsed = self._make_parsed_api()
        tested = json.dumps(["listPets", "createPet"])
        result = json.loads(
            compute_coverage(parsed, tested_operation_ids_json=tested)
        )
        assert "operation_coverage" in result
        assert result["operation_coverage"]["tested"] == 2
        assert result["operation_coverage"]["total_operations"] == 3
        assert "getPet" in result["operation_coverage"]["untested"]

    def test_usability_with_scripts(self):
        """Usability metrics computed when both scripts provided."""
        parsed = self._make_parsed_api()
        original = "test('a', () => { expect(1).toBe(1); });"
        final = "test('a', () => { expect(2).toBe(2); });"
        result = json.loads(
            compute_coverage(parsed, original_script=original, final_script=final)
        )
        assert "usability" in result
        assert "levenshtein_distance" in result["usability"]
        assert "similarity" in result["usability"]

    def test_empty_inputs(self):
        """Empty lists should not crash — returns safe defaults."""
        parsed = self._make_parsed_api()
        result = json.loads(compute_coverage(parsed))
        assert "scenario_coverage" in result
        assert "operation_coverage" in result


# =============================================================================
# TestToolsModule
# =============================================================================


class TestToolsModule:
    def test_mastest_tools_list(self):
        """MASTEST_TOOLS should contain at least 3 tools (parse + check + compute + playwright)."""
        from src.app.agents.api.tools import MASTEST_TOOLS

        assert len(MASTEST_TOOLS) >= 3

    def test_backends_created(self):
        """All three backends should be instantiated."""
        from src.app.agents.api.tools import composite_backend, file_backend, shell_backend

        assert composite_backend is not None
        assert file_backend is not None
        assert shell_backend is not None

    def test_workspace_dir_is_api(self):
        """workspace_dir in tools module should resolve to .../workspace/api."""
        from src.app.agents.api.tools import workspace_dir

        assert workspace_dir.name == "api"
        assert workspace_dir.parent.name == "workspace"
