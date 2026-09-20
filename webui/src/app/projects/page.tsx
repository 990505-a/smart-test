import { redirect } from "next/navigation";

// 旧入口跳转。2026-08 用例存储 MD 化之后，「项目」不再是一张表的记录：
// 一个项目 = workspace/default/cases/<项目名>.md，所以项目管理就是 /cases 的
// 文档列表（新建/重命名/删除文档即管理项目）。独立的项目/附件/配置模块
// （表 + API + 无 UI）已于 2026-09-18 删除。
export default function ProjectsPage() {
  redirect("/cases");
}
