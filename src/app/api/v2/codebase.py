"""Codebase-graph routes: managed repos, indexing, graph data, scheduling.

Platform module. The exe is reached over stdio MCP for management ops and via
its built-in HTTP UI (:9749, spawned on demand) for precomputed graph layout
data. The optional post-index impact analysis (增量影响分析) runs the codebase
agent headlessly — see services/codebase_analysis_service.py.
"""

from fastapi import APIRouter, BackgroundTasks, Query
from pydantic import BaseModel

from src.app.api.v2.auth import CurrentUserDep
from src.app.db.schemas.common import SuccessResponse
from src.app.services import codebase_service

router = APIRouter(prefix="/codebase")


class RepoCreate(BaseModel):
    repo_path: str
    display_name: str | None = None
    file_type_mode: str = "all"  # all | include | exclude
    file_types: list[str] = []
    auto_increment: bool = True
    auto_analyze: bool = False


class RepoUpdate(BaseModel):
    display_name: str | None = None
    file_type_mode: str | None = None
    file_types: list[str] | None = None
    auto_increment: bool | None = None
    auto_analyze: bool | None = None


class IndexRequest(BaseModel):
    mode: str = "fast"  # fast | moderate | full


class ScheduleUpdate(BaseModel):
    enabled: bool
    interval_hours: int
    # 缺省 None = 不改动该开关（老客户端只传前两个字段时保持现状）
    analyze_enabled: bool | None = None


@router.get("/status", response_model=SuccessResponse, summary="服务状态 + 已索引项目 + 图守护")
async def codebase_status(user: CurrentUserDep):
    return SuccessResponse(success=True, data=await codebase_service.status())


@router.post("/install", response_model=SuccessResponse,
             summary="下载并安装/升级官方 codebase-memory（按当前平台）")
async def codebase_install(force: bool = Query(False, description="true = 重装/升级到配置的版本"),
                           version: str | None = Query(None, description="留空用 CODEBASE_VERSION")):
    from src.app.services import cbm_install

    result = await cbm_install.install_async(version, force=force)
    if not result.get("success") and "success" in result:
        return SuccessResponse(success=False, data=result)
    return SuccessResponse(success=True, data=result)


@router.get("/repos", response_model=SuccessResponse, summary="受管仓库列表（含建库状态）")
async def codebase_repos(user: CurrentUserDep):
    return SuccessResponse(success=True, data=await codebase_service.list_repos())


@router.post("/repos", response_model=SuccessResponse, summary="添加受管仓库")
async def codebase_add_repo(req: RepoCreate, user: CurrentUserDep):
    return SuccessResponse(success=True,
                           data=await codebase_service.add_repo(
                               req.repo_path, req.display_name,
                               req.file_type_mode, req.file_types, req.auto_increment,
                               req.auto_analyze))


@router.patch("/repos/{repo_id}", response_model=SuccessResponse, summary="更新仓库配置")
async def codebase_update_repo(repo_id: str, req: RepoUpdate, user: CurrentUserDep):
    return SuccessResponse(success=True,
                           data=await codebase_service.update_repo(
                               repo_id, display_name=req.display_name,
                               file_type_mode=req.file_type_mode,
                               file_types=req.file_types,
                               auto_increment=req.auto_increment,
                               auto_analyze=req.auto_analyze))


@router.delete("/repos/{repo_id}", response_model=SuccessResponse, summary="移除仓库（可选删索引）")
async def codebase_delete_repo(repo_id: str, user: CurrentUserDep,
                               delete_index: bool = Query(False, description="同时删除图谱索引")):
    return SuccessResponse(success=True,
                           data=await codebase_service.delete_repo(repo_id, delete_index))


@router.get("/repos/{repo_id}/cbmignore", response_model=SuccessResponse, summary="查看仓库实际生效的 .cbmignore")
async def codebase_read_cbmignore(repo_id: str, user: CurrentUserDep):
    return SuccessResponse(success=True, data=await codebase_service.read_cbmignore(repo_id))


@router.post("/repos/{repo_id}/index", response_model=SuccessResponse, summary="触发索引（后台）")
async def codebase_start_index(repo_id: str, req: IndexRequest, user: CurrentUserDep):
    return SuccessResponse(success=True,
                           data=await codebase_service.start_index(repo_id, req.mode))


@router.get("/runs", response_model=SuccessResponse, summary="索引运行历史")
async def codebase_runs(user: CurrentUserDep, repo_id: str | None = None,
                        limit: int = Query(30, ge=1, le=200)):
    return SuccessResponse(success=True,
                           data=await codebase_service.list_runs(repo_id, limit))


@router.get("/graph-data", response_model=SuccessResponse, summary="图谱可视化数据（nodes+edges）")
async def codebase_graph_data(user: CurrentUserDep, project: str,
                              max_nodes: int = Query(2000, ge=10, le=5000)):
    result = await codebase_service.graph_layout(project, max_nodes)
    # 解包一层：成功时 data 直接是 layout JSON（nodes/edges），失败时是错误对象
    return SuccessResponse(success=True,
                           data=result.get("data") if result.get("success") else result)


@router.get("/graph-subgraph", response_model=SuccessResponse, summary="范围视图图数据（目录子图/符号邻域,大图专用）")
async def codebase_graph_subgraph(user: CurrentUserDep, project: str,
                                  mode: str = Query("dir", pattern="^(dir|symbol)$"),
                                  value: str = Query(..., min_length=1, max_length=300)):
    result = await codebase_service.graph_subgraph(project, mode, value)
    return SuccessResponse(success=True,
                           data=result.get("data") if result.get("success") else result)


@router.get("/schedule", response_model=SuccessResponse, summary="定时增量配置")
async def codebase_schedule(user: CurrentUserDep):
    return SuccessResponse(success=True, data=await codebase_service.get_schedule())


@router.put("/schedule", response_model=SuccessResponse, summary="更新定时增量配置")
async def codebase_save_schedule(req: ScheduleUpdate, user: CurrentUserDep):
    return SuccessResponse(success=True,
                           data=await codebase_service.save_schedule(
                               req.enabled, req.interval_hours, req.analyze_enabled))


@router.post("/schedule/trigger", response_model=SuccessResponse, summary="立即执行一轮增量（后台）")
async def codebase_trigger_round(background: BackgroundTasks, user: CurrentUserDep):
    background.add_task(codebase_service.run_incremental_round, trigger="manual")
    return SuccessResponse(success=True, data={"success": True, "started": True})


# ---------------------------------------------------------------------------
# 增量影响分析（无头 codebase_agent 的产物）
# ---------------------------------------------------------------------------

@router.get("/impact-reports", response_model=SuccessResponse, summary="影响报告列表")
async def codebase_impact_reports(user: CurrentUserDep, repo_id: str | None = None,
                                  limit: int = Query(50, ge=1, le=200)):
    from src.app.services import codebase_analysis_service as analysis
    return SuccessResponse(success=True,
                           data=await analysis.list_reports(repo_id, limit))


@router.get("/impact-reports/{report_id}", response_model=SuccessResponse, summary="影响报告详情")
async def codebase_impact_report(report_id: str, user: CurrentUserDep):
    from src.app.services import codebase_analysis_service as analysis
    return SuccessResponse(success=True, data=await analysis.get_report(report_id))


@router.delete("/impact-reports/{report_id}", response_model=SuccessResponse, summary="删除影响报告")
async def codebase_delete_impact_report(report_id: str, user: CurrentUserDep):
    from src.app.services import codebase_analysis_service as analysis
    return SuccessResponse(success=True, data=await analysis.delete_report(report_id))


@router.post("/repos/{repo_id}/analyze", response_model=SuccessResponse, summary="立即生成影响分析（后台）")
async def codebase_analyze_repo(repo_id: str, background: BackgroundTasks,
                               user: CurrentUserDep):
    """手动触发：即使本轮没有文件变更也照跑（force=True）。

    仓库未开启 auto_analyze 也能手动跑——手动是显式意图，不受定时开关限制。
    """
    from src.app.services import codebase_analysis_service as analysis
    background.add_task(analysis.run_impact_analysis, repo_id,
                        trigger="manual", force=True)
    return SuccessResponse(success=True, data={"success": True, "started": True})
