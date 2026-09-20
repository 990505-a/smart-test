/* 「RAG 设置」页逻辑（平台注入到 LightRAG 自带界面里的静态页，无构建步骤）。
 *
 * 数据全走平台后端（window.__SMART_TEST__.platformApi，由启动器生成
 * rag-settings-config.js 写入）：LightRAG 本体没有"改配置"的 API，配置的事实源
 * 是平台的 .env + 知识库注册表文件，重启由平台转调启动器完成。
 */
(function () {
  "use strict";

  var cfg = window.__SMART_TEST__ || {};
  var API = (cfg.platformApi || "http://127.0.0.1:5012").replace(/\/+$/, "");
  var RAG_PAGE = cfg.platformRagPage || "";
  var MASK = "********";
  var FIELDS = [
    "llm_base_url", "llm_model", "llm_api_key",
    "embedding_base_url", "embedding_model", "embedding_dim", "embedding_api_key",
  ];
  var kbRows = [];

  function $(id) { return document.getElementById(id); }

  function alertBox(msg, kind) {
    var el = $("alert");
    el.hidden = !msg;
    el.className = "alert" + (kind ? " " + kind : "");
    el.textContent = msg || "";
  }

  function api(path, options) {
    return fetch(API + path, Object.assign({
      headers: { "Content-Type": "application/json" },
    }, options || {})).then(function (resp) {
      return resp.json().then(function (body) {
        if (!resp.ok) {
          throw new Error((body && (body.detail || body.message)) || ("HTTP " + resp.status));
        }
        return body && body.data !== undefined ? body.data : body;
      });
    });
  }

  function collectValues() {
    var values = {};
    FIELDS.forEach(function (id) {
      var el = $(id);
      if (!el) return;
      var value = el.value.trim();
      // 蒙版的密钥没被动过就别回写（后端也会拦，但少发一份更干净）
      if (value && value === MASK) return;
      values["lightrag_" + id] = value;
    });
    return values;
  }

  function readKbRows() {
    return Array.prototype.map.call($("kb-rows").querySelectorAll("tr"), function (tr) {
      return {
        key: tr.querySelector('[data-f="key"]').value.trim(),
        label: tr.querySelector('[data-f="label"]').value.trim(),
        port: parseInt(tr.querySelector('[data-f="port"]').value, 10) || 0,
        description: tr.querySelector('[data-f="description"]').value.trim(),
      };
    });
  }

  function kbRow(row) {
    var tr = document.createElement("tr");
    // description 用隐藏字段：它在平台「知识库」页的服务卡上展示，但表格里再放一列太挤。
    // 必须存在于 DOM 里——读写两边的数据保持完整，保存清单时不会被清空。
    tr.innerHTML =
      '<td><input data-f="key" value="" placeholder="ruoyi" />' +
      '<input type="hidden" data-f="description" value="" /></td>' +
      '<td><input data-f="label" value="" placeholder="ruoyi 后台" /></td>' +
      '<td><input data-f="port" value="" placeholder="5021" /></td>' +
      '<td class="hint-cell" data-f="hint">保存后显示</td>' +
      '<td class="hint-cell" data-f="status">—</td>' +
      '<td class="row-actions">' +
      '  <button class="btn" data-act="start">启动</button>' +
      '  <button class="btn" data-act="restart">重启</button>' +
      '  <button class="btn" data-act="stop">停止</button>' +
      '  <button class="btn danger" data-act="remove">删除</button>' +
      "</td>";
    ["key", "label", "port", "description"].forEach(function (field) {
      var el = tr.querySelector('[data-f="' + field + '"]');
      if (el) el.value = row[field] || "";
    });
    tr.querySelector('[data-f="hint"]').textContent = row.data_dir || "保存后显示";
    renderStatus(tr, row);
    tr.querySelector("td:last-child").addEventListener("click", function (ev) {
      var act = ev.target.getAttribute("data-act");
      if (!act) return;
      if (act === "remove") {
        tr.remove();
        alertBox("已从清单里移除（还没保存）。数据仍在原目录里，把同一行加回来即可恢复。");
        return;
      }
      var key = tr.querySelector('[data-f="key"]').value.trim();
      if (!key) { alertBox("先填 key 再操作服务", "err"); return; }
      ev.target.disabled = true;
      api("/api/v2/rag/service/" + encodeURIComponent(key) + "/" + act, { method: "POST" })
        .then(function (data) {
          alertBox(act + " 已下发：" + JSON.stringify(data.results || {}));
          setTimeout(load, 4000);
        })
        .catch(function (err) { alertBox(String(err.message || err), "err"); })
        .finally(function () { ev.target.disabled = false; });
    });
    return tr;
  }

  function renderStatus(tr, row) {
    var cell = tr.querySelector('[data-f="status"]');
    if (row.reachable === undefined || row.reachable === null) { cell.textContent = "—"; return; }
    cell.innerHTML = '<span class="dot ' + (row.reachable ? "on" : "off") + '"></span>' +
      (row.reachable ? "在线" : "未启动") +
      (row.documents !== undefined && row.documents !== null ? " · " + row.documents + " 篇" : "");
    if (row.error && !row.reachable) cell.title = row.error;
  }

  function render(data) {
    var values = data.values || {};
    FIELDS.forEach(function (id) {
      var el = $(id);
      if (el) el.value = values["lightrag_" + id] || "";
    });
    var eff = data.effective || {};
    $("llm-inherit").textContent =
      (eff.model || "（未配置）") + " @ " + (eff.base_url || "—") +
      (eff.api_key_set ? "" : "（缺 API Key）");

    kbRows = data.kbs || [];
    var tbody = $("kb-rows");
    tbody.innerHTML = "";
    (data.kbs || []).forEach(function (row) { tbody.appendChild(kbRow(row)); });

    var svc = data.service || {};
    $("service-info").innerHTML =
      "工作目录：<code>" + (svc.working_dir || "—") + "</code>（各库按 workspace 分子目录） · " +
      "新库端口范围：" + (svc.port_range || "—") + " · " +
      "默认库 API：" + "<code>" + (svc.default_base_url || "—") + "</code>";
    $("add-kb").dataset.suggest = JSON.stringify(data.next_kb || {});
  }

  function load() {
    api("/api/v2/rag/settings").then(function (data) {
      try {
        render(data);
      } catch (err) {
        // 渲染错误与"读不到配置"是两回事：前者是页面自身的 bug，别伪装成后端不可达
        alertBox("页面渲染失败（" + String(err && err.message || err) + "）", "err");
        return null;
      }
      return api("/api/v2/rag/kbs");
    }).then(function (rows) {
      if (!rows) return;
      // 用实时状态刷新每一行（上面的 settings 只给静态清单）
      var byKey = {};
      (rows || []).forEach(function (r) { byKey[r.key] = r; });
      Array.prototype.forEach.call($("kb-rows").querySelectorAll("tr"), function (tr) {
        var key = tr.querySelector('[data-f="key"]').value.trim();
        if (byKey[key]) {
          tr.querySelector('[data-f="hint"]').textContent = byKey[key].data_dir || "";
          renderStatus(tr, byKey[key]);
        }
      });
      // 成功提示不该在这里被清掉：保存后 guard() 会回调 load() 刷新，
      // 一闪而过的"已保存"等于没提示。只在出错时覆盖它。
    }).catch(function (err) {
      alertBox("读不到平台配置（" + API + "）：" + String(err.message || err) +
        " —— 平台后端(:5012)没起的话，这个页面只能看，不能改。", "err");
    });
  }

  function saveValues() {
    var payload = { values: collectValues() };
    if (!Object.keys(payload.values).length) {
      return Promise.resolve();
    }
    return api("/api/v2/rag/settings", { method: "PUT", body: JSON.stringify(payload) })
      .then(function (data) {
        alertBox((data && data.note) || "已保存", "ok");
        return true;
      });
  }

  function saveKbs() {
    return api("/api/v2/rag/kbs", {
      method: "PUT", body: JSON.stringify({ kbs: readKbRows() }),
    }).then(function (data) {
      alertBox((data && data.note) || "知识库清单已保存", "ok");
      return true;
    });
  }

  function restartAll() {
    return api("/api/v2/rag/service/all/restart", { method: "POST" }).then(function (data) {
      // 服务控制是异步的：提示压成一句，明细留在控制台日志里（:5010）
      var keys = Object.keys(data.results || {});
      alertBox("已下发重启：" + keys.join("、") +
        "（10-30 秒后刷新本页可看状态；失败时看启动器 :5010 的日志）", "ok");
    });
  }

  function guard(button, promise) {
    button.disabled = true;
    // 先把上一条提示清掉：这次操作的结果才是用户要看的
    alertBox("");
    Promise.resolve(promise)
      .catch(function (err) { alertBox(String(err.message || err), "err"); })
      .finally(function () { button.disabled = false; load(); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (RAG_PAGE) $("platform-link").href = RAG_PAGE;
    $("add-kb").addEventListener("click", function () {
      var suggest = JSON.parse($("add-kb").dataset.suggest || "{}");
      var tr = kbRow({ key: suggest.key || "", label: suggest.label || "",
                       port: suggest.port || "", description: suggest.description || "" });
      $("kb-rows").appendChild(tr);
      tr.querySelector('[data-f="key"]').focus();
    });
    $("save-kbs").addEventListener("click", function (ev) { guard(ev.target, saveKbs()); });
    $("save-values").addEventListener("click", function (ev) { guard(ev.target, saveValues()); });
    $("save-restart").addEventListener("click", function (ev) {
      guard(ev.target, saveValues().then(saveKbs).then(restartAll));
    });
    $("reload").addEventListener("click", function () { load(); });
    load();
  });
})();
