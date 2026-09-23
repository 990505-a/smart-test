import { apiV2Url } from "@/lib/api-client";

/**
 * 把 Markdown 里指向**本地文件路径**的图片改写成后端 /files 端点的 URL。
 *
 * 为什么需要：智能体/工具会把产物（飞书授权二维码、截图等）落在 workspace 下，
 * 回复里用本地绝对路径引用（`![二维码](E:\...\workspace\default\agent\qr.png)`）。
 * 浏览器加载不了本地路径；而且 rehype-sanitize 的协议白名单会把 `E:` 当成
 * 非法 scheme 直接剥掉 src —— 所以必须在解析/清洗**之前**改写正文。
 *
 * 只改写三种无歧义的本地形态；http(s)/data:/其他相对路径原样保留。
 */

/** Windows 盘符路径（E:\…）、UNC（\\server\…）、仓库根相对（workspace/…） */
const LOCAL_PATH_SRC = /^(?:[A-Za-z]:[\\/]|\\\\|workspace[\\/])/i;

function rewriteSrc(src: string): string {
  if (!LOCAL_PATH_SRC.test(src)) return src;
  return apiV2Url(`/files?path=${encodeURIComponent(src)}`);
}

/** Markdown 图片 `![alt](url)`（含 `![alt](<url>)` 尖括号形态）。 */
const MD_IMAGE_PLAIN = /(!\[[^\]]*\]\()([^)\s]+)(\))/g;
const MD_IMAGE_ANGLED = /(!\[[^\]]*\]\(<)([^>]+)(>\))/g;
/** 内嵌 HTML <img src="…"> / <img src='…'>（rehype-raw 会解析它们）。 */
const HTML_IMG_SRC = /(<img\b[^>]*\bsrc=)(["'])([^"']*)(\2)/gi;

export function rewriteLocalImages(content: string): string {
  if (!content) return content;
  return content
    .replace(MD_IMAGE_ANGLED, (_m, pre: string, src: string, post: string) =>
      `${pre}${rewriteSrc(src)}${post}`)
    .replace(MD_IMAGE_PLAIN, (_m, pre: string, src: string, post: string) =>
      `${pre}${rewriteSrc(src)}${post}`)
    .replace(HTML_IMG_SRC, (_m, pre: string, quote: string, src: string) =>
      `${pre}${quote}${rewriteSrc(src)}${quote}`);
}
