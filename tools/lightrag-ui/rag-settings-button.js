/* 在 LightRAG 自带 WebUI 的右下角挂一个「RAG 设置」入口按钮。
 *
 * 为什么用浮层按钮而不是改它的导航栏：官方的 WebUI 是一个压缩过的静态构建
 * （index-<hash>.js），改导航等于改它的产物——升级就碎。这里只在 index.html 里
 * 注入一行 <script>（见 launcher.py 的 _sync_lightrag_ui），与本文件同级加一个
 * 浮动入口，升级后由启动器自动重新注入。
 */
(function () {
  "use strict";
  if (document.getElementById("smart-test-rag-settings-btn")) return;

  var style = document.createElement("style");
  style.textContent = [
    "#smart-test-rag-settings-btn{position:fixed;right:18px;bottom:18px;z-index:2147483000;",
    "display:flex;align-items:center;gap:6px;padding:8px 14px;border-radius:999px;",
    "background:#2563eb;color:#fff;font:13px/1 system-ui,'PingFang SC','Microsoft YaHei',sans-serif;",
    "text-decoration:none;box-shadow:0 6px 18px rgba(0,0,0,.28);opacity:.9}",
    "#smart-test-rag-settings-btn:hover{opacity:1}",
  ].join("");
  document.head.appendChild(style);

  function mount() {
    var link = document.createElement("a");
    link.id = "smart-test-rag-settings-btn";
    // 用相对地址：LightRAG 可能挂在反代的子路径下（LIGHTRAG_API_PREFIX），
    // 绝对地址 /webui/... 在那种部署里指不到。
    link.href = "rag-settings.html";
    link.textContent = "⚙ RAG 设置";
    link.title = "模型 / Embedding / 知识库清单（智能测试平台）";
    document.body.appendChild(link);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
