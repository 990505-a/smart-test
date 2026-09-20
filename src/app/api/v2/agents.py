"""Agent assembly routes —— 智能体 / 能力 / 工具 / 技能 的装配目录.

层级：**智能体 → 能力 → 工具 / 技能 / 权限**。全部是可编辑的用户数据，存在
``workspace/<space>/assembly.json``（``services/assembly_service.py``）；代码里的
能力清单只是首次播种用的种子 + 工具候选池（工具是 Python 函数，界面造不出来）。

- ``GET /agents``            目录（智能体 + 能力 + 工具候选池 + 技能候选池）
- ``PUT /agents/catalog``    整份保存（页面把编辑后的完整目录发回来）
- ``DELETE /agents/catalog`` 恢复默认（删文件、重新播种）

生效时机：保存完**下一轮对话**就生效，不用重启 LangGraph 进程 —— 中间件按
``configurable.agent_id`` 在每次模型调用前重算工具面、能力段提示词与技能清单，
审批走 ``interrupt_on`` 的 when 谓词现查（见 ``middleware/assembly.py``）。
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.app.api.v2.auth import CurrentUserDep
from src.app.db.schemas.common import SuccessResponse

router = APIRouter(prefix="/agents")


class CatalogUpdate(BaseModel):
    """整份覆盖装配目录（页面把编辑后的 agents + capabilities 发回来）。"""

    agents: list[dict] = Field(default_factory=list, description="智能体列表")
    capabilities: list[dict] = Field(default_factory=list, description="能力列表")


@router.get("", response_model=SuccessResponse, summary="装配目录（智能体/能力/候选池）")
async def list_agents(user: CurrentUserDep):
    """"现在有哪些智能体、各自装了什么、能装什么" 的唯一权威来源。"""
    return SuccessResponse(success=True, data=catalog_view())


@router.put("/catalog", response_model=SuccessResponse, summary="保存装配目录")
async def put_catalog(payload: CatalogUpdate, user: CurrentUserDep):
    """整份保存。

    引用了不存在的东西（工具符号 / 技能目录 / 能力 key）会在 ``ignored`` 里回报并丢掉：
    界面与后端版本不一致时宁可少改，也不要把配错的目录存进去。
    """
    from src.app.services import assembly_service as asm

    incoming = asm.Catalog.from_raw(payload.model_dump())
    if not incoming.capabilities:
        # 一个能力都没有的话，保留代码清单播种出来的那套（否则智能体是个空壳）
        incoming = asm.Catalog(agents=incoming.agents,
                               capabilities=asm.default_catalog().capabilities)
    if not incoming.agents:
        # 至少留一个智能体，否则对话页没有可选项；它装配的就是这次提交的这些能力
        incoming = asm.Catalog(
            agents=(asm.AgentDef(
                id=asm.DEFAULT_AGENT_ID,
                label=asm.DEFAULT_AGENT_LABEL,
                description=asm.DEFAULT_AGENT_DESCRIPTION,
                capabilities=tuple(c.key for c in incoming.capabilities),
            ),),
            capabilities=incoming.capabilities,
        )
    clean, ignored = asm.validate_catalog(incoming)
    if not clean.agents:
        fallback = asm.default_catalog()
        clean = asm.Catalog(agents=fallback.agents, capabilities=clean.capabilities or fallback.capabilities)

    saved = asm.save_catalog(clean)
    data = catalog_view(saved)
    data["ignored"] = ignored
    data["note"] = "已保存，下一轮对话起生效（无需重启服务）"
    return SuccessResponse(success=True, data=data)


@router.post("/reload", response_model=SuccessResponse, summary="重启 LangGraph（重载工具池）")
async def reload_agent_service(user: CurrentUserDep):
    """重启 LangGraph 服务，让**新增的工具**进入候选池。

    为什么工具要重启、技能不用：技能是目录里的 SKILL.md，每轮现扫；工具是 Python
    函数，在 graph 编译期被注册进 ``ToolNode``，进程内还有候选池与符号解析缓存。
    所以"在代码清单里加了个工具"必须重启才看得到（技能上传后不用）。

    ⚠️ 重启会中断正在跑的对话（checkpointer 是进程内存），所以页面上要点确认。
    容器模式没有启动器（:5010），这时如实报错让用户手动重启。
    """
    from src.app.core import integrations
    from src.app.services import assembly_service as asm

    before = len(asm.tool_catalog())
    result = await integrations.launcher_action("langgraph", "restart")
    if not result.get("success"):
        return SuccessResponse(success=False, data={
            "restarted": False,
            "error": result["error"],
            "hint": "容器模式请手动重启 langgraph 服务；本机模式请在启动器控制台(:5010)点 restart。",
        })
    payload = (result.get("data") or {}) if isinstance(result.get("data"), dict) else {}
    return SuccessResponse(success=True, data={
        "restarted": True,
        "pid": payload.get("pid"),
        "tools_before": before,
        "note": "已重启 LangGraph：新进程约 5-10 秒起来，之后刷新本页即可看到新增的工具。"
                "正在跑的对话会被中断。",
    })


@router.delete("/catalog", response_model=SuccessResponse, summary="恢复默认装配目录")
async def delete_catalog(user: CurrentUserDep):
    """删掉目录文件，回到代码清单播种出来的那套（一个通用智能体 + 四项能力）。"""
    from src.app.services import assembly_service as asm

    asm.reset_catalog()
    data = catalog_view()
    data["note"] = "已恢复默认：一个「通用测试助手」+ 代码清单里的四项能力，下一轮对话起生效"
    return SuccessResponse(success=True, data=data)


def catalog_view(catalog=None) -> dict:
    """目录 + 候选池（GET / PUT / DELETE 共用，页面直接照着渲染）。"""
    from src.app.services import assembly_service as asm

    catalog = catalog or asm.load_catalog()
    caps = []
    for cap in catalog.capabilities:
        names = asm.tool_names(cap)
        caps.append({
            **cap.to_dict(),
            "tool_names": list(names),
            "tool_count": len(names),
        })
    return {
        "agents": [a.to_dict() for a in catalog.agents],
        "capabilities": caps,
        "tool_catalog": asm.tool_catalog(),
        "skill_catalog": asm.skill_catalog(),
        "default_agent_id": asm.DEFAULT_AGENT_ID,
        "file": str(asm.assembly_path()),
        # 文件不存在 = 还没改过（"恢复默认"的判定也看它）
        "is_default": not asm.assembly_path().exists(),
    }
