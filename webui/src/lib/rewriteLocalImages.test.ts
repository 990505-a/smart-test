/**
 * rewriteLocalImages 单元测试：本地路径图片改写为 /files 端点 URL。
 *
 * 背景（2026-09-22 真实事故）：智能体把飞书授权二维码存到 workspace 后，
 * 回复里写 `![飞书授权二维码](E:\...\workspace\default\agent\qr.png)`，
 * 浏览器加载不了本地路径 + rehype-sanitize 把 "E:" 当非法 scheme 剥掉 src，
 * 渲染成裂图。
 */
import { describe, expect, it } from "vitest";
import { rewriteLocalImages } from "./rewriteLocalImages";

const API = "http://localhost:5012/api/v2";

describe("rewriteLocalImages", () => {
  it("改写 Windows 绝对路径图片（事故原文形态）", () => {
    const md = "看图：![飞书授权二维码](E:\\test\\workspace\\default\\agent\\qr.png)";
    const out = rewriteLocalImages(md);
    expect(out).toBe(
      `看图：![飞书授权二维码](${API}/files?path=${encodeURIComponent("E:\\test\\workspace\\default\\agent\\qr.png")})`,
    );
  });

  it("改写正斜杠绝对路径与 workspace/ 前缀相对路径", () => {
    expect(rewriteLocalImages("![](D:/shots/a.png)")).toContain(`${API}/files?path=`);
    expect(rewriteLocalImages("![](workspace/default/cases/x.png)")).toContain(
      `${API}/files?path=${encodeURIComponent("workspace/default/cases/x.png")}`,
    );
  });

  it("改写尖括号形态与内嵌 HTML img src", () => {
    expect(rewriteLocalImages("![](<E:\\a b\\c.png>)")).toContain(`${API}/files?path=`);
    expect(
      rewriteLocalImages('<img src="E:\\\\srv\\\\share\\\\q.png" alt="qr">'),
    ).toContain(`${API}/files?path=`);
  });

  it("不动 http(s)/data:/普通相对路径", () => {
    const md = "![远程](https://a.com/x.png) ![数据](data:image/png;base64,xx) ![相对](./local.png)";
    expect(rewriteLocalImages(md)).toBe(md);
  });

  it("链接（非图片）里的本地路径不受影响", () => {
    const md = "[打开](E:\\docs\\a.md)";
    expect(rewriteLocalImages(md)).toBe(md);
  });
});
