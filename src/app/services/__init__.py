"""Platform services package.

Legacy API-execution services (OpenAPIParser / APITestExecutor /
ScenarioExecutionEngine) were removed together with the legacy
Web/API automation modules (2026-08). This package now only hosts
lightweight service modules imported directly by path, e.g.::

    from src.app.services.auth_service import AuthService
"""
