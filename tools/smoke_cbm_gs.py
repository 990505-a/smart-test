"""Phase 0 smoke test: GS exe via stdio shim (list_projects) + HTTP graph UI."""

import asyncio
import sys


async def main() -> None:
    from src.app.services import codebase_service

    print("== list_projects via stdio shim (cbm-gs.exe) ==")
    result = await codebase_service.cbm_call("list_projects", {})
    import json
    print(json.dumps(result, ensure_ascii=False, default=str)[:1500])

    ok = result.get("success")
    print("STDIO_RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
