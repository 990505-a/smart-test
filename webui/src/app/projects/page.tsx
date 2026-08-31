import { redirect } from "next/navigation";

// 项目管理已合并进 /cases（用例页的项目管理器），旧入口跳转
export default function ProjectsPage() {
  redirect("/cases");
}
