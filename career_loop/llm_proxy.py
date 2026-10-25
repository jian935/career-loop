"""本地 LLM 代理（零第三方依赖，只用标准库）。

为什么需要它
------------
浏览器里的网页 demo 想调用 OpenAI 兼容接口，有两个硬障碍：

1. **CORS**：多数服务商不给 ``Access-Control-Allow-Origin``，浏览器直接
   ``fetch`` 会被拦，而且报错只出现在浏览器控制台里，用户根本看不到原因。
2. **Key 不该进网页**：让用户把 API Key 粘进网页表单，等于把 Key 交给任意
   一个在该页面里运行的脚本。

这个代理跑在**本机 127.0.0.1**，Key 留在本地环境变量 / ``.env`` 里，
网页只跟本机说话——两个障碍一起解决。

安全设计
--------
- 只绑 ``127.0.0.1``，不对外暴露；
- 启动时生成一次性 token，调用必须带上（``X-CL-Token`` 头或 ``?token=``），
  防止本机其它网页盗用你的 Key 去计费；
- 请求体大小上限，避免被当成免费接口刷；
- 模型固定用本地配置的，**不接受网页指定**（防止网页把请求指向更贵的模型）。

用法::

    career-loop llm-proxy                    # 默认 127.0.0.1:8787
    career-loop llm-proxy --port 9000
    career-loop llm-proxy --no-cors-check    # 允许任意 Origin（默认只放行 null/file/http://localhost）
"""

from __future__ import annotations

import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .matching.llm import LLM, LLMError

DEFAULT_PORT = 8787
MAX_BODY = 200_000          # 20 万字节，够放 12k 字中文 JD + 提示词
ALLOWED_ORIGINS = ("null", "file://", "http://localhost", "http://127.0.0.1")


def _is_origin_allowed(origin: str, allow_any: bool) -> bool:
    if allow_any:
        return True
    if not origin:
        return True          # 同源 / curl / 无 Origin 的请求
    low = origin.lower()
    return any(low.startswith(p) for p in ALLOWED_ORIGINS)


class _Handler(BaseHTTPRequestHandler):
    server_version = "career-loop-llm-proxy/1.0"
    llm: LLM
    token: str
    allow_any_origin: bool

    # ---------- 基础工具 ----------
    def _cors(self) -> str | None:
        origin = self.headers.get("Origin", "")
        if not _is_origin_allowed(origin, self.allow_any_origin):
            return None
        if origin and not self.allow_any_origin:
            return origin
        return "*"

    def _send(self, code: int, payload: dict, origin: str | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CL-Token")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):        # 静音默认的 stderr 访问日志
        pass

    def _drain(self, length: int) -> None:
        """把请求体读掉丢弃（最多 4MB），避免提前关连接导致客户端拿到 reset。"""
        remaining = min(length, 4_000_000)
        while remaining > 0:
            chunk = self.rfile.read(min(65536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

    # ---------- 路由 ----------
    def do_OPTIONS(self):                     # noqa: N802
        origin = self._cors()
        if origin is None:
            self._send(403, {"error": "origin not allowed"})
            return
        self._send(204, {}, origin)

    def do_GET(self):                         # noqa: N802
        origin = self._cors()
        if origin is None:
            self._send(403, {"error": "origin not allowed"})
            return
        if self.path.split("?")[0] == "/health":
            self._send(200, {
                "ok": True,
                "has_key": self.llm.available,
                "model": self.llm.model,
                "base_url": self.llm.base_url,
            }, origin)
            return
        self._send(404, {"error": "not found"}, origin)

    def do_POST(self):                        # noqa: N802
        origin = self._cors()
        if origin is None:
            self._send(403, {"error": "origin not allowed"})
            return
        if self.path.split("?")[0] != "/llm":
            self._send(404, {"error": "not found"}, origin)
            return

        # 鉴权：token 可以在头里，也可以在 query 里
        sent = self.headers.get("X-CL-Token", "")
        if "token=" in self.path:
            sent = self.path.split("token=")[1].split("&")[0]
        if not secrets.compare_digest(sent, self.token):
            self._send(401, {"error": "bad token"}, origin)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            # 必须先把请求体读完（丢弃），否则服务器提前关闭连接，
            # 客户端收到的是 connection reset 而不是我们想给的 413。
            self._drain(length)
            msg = (f"body size {length} out of range (max {MAX_BODY})"
                   if length > MAX_BODY else "empty body")
            body = json.dumps({"error": msg}, ensure_ascii=False).encode("utf-8")
            self.send_response(413 if length > MAX_BODY else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.end_headers()
            self.wfile.write(body)
            return

        try:
            req = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send(400, {"error": f"bad json: {exc}"}, origin)
            return

        system = req.get("system") or ""
        user = req.get("user") or ""
        if not user:
            self._send(400, {"error": "missing 'user'"}, origin)
            return

        try:
            text = self.llm.chat(system, user, temperature=float(req.get("temperature", 0.2)))
        except LLMError as exc:
            self._send(502, {"error": str(exc)}, origin)
            return
        except Exception as exc:               # noqa: BLE001 — 代理层要兜住一切
            self._send(502, {"error": f"{type(exc).__name__}: {exc}"}, origin)
            return

        self._send(200, {"text": text, "model": self.llm.model,
                         "stats": dict(self.llm.stats)}, origin)


def _serve_quietly(httpd) -> None:
    """serve_forever 的安静包装：关停时 Windows 会抛 socket 选择器错误，吞掉它。"""
    try:
        httpd.serve_forever()
    except OSError:
        pass
    except KeyboardInterrupt:
        pass


def serve(port: int = DEFAULT_PORT, token: str | None = None, allow_any_origin: bool = False,
          open_browser: bool = True) -> None:
    """启动代理并阻塞。返回前会打印连接方式。"""
    llm = LLM()
    tok = token or secrets.token_urlsafe(16)
    handler = type("Handler", (_Handler,), {
        "llm": llm, "token": tok, "allow_any_origin": allow_any_origin,
    })
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}"

    print("career-loop 本地 LLM 代理已启动")
    print(f"  地址    {url}")
    print(f"  Token   {tok}")
    print(f"  模型    {llm.model}  （上游 {llm.base_url}）")
    if not llm.available:
        print("  ⚠ 没检测到 API Key（OPENAI_API_KEY / DEEPSEEK_API_KEY）——"
              "网页端调用会返回 502，先配好 Key 再试。")
    print("  网页端填：地址 = 上述地址，Token = 上述 Token")
    print("  Ctrl-C 停止")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:                     # noqa: BLE001
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    except OSError:
        pass
    finally:
        httpd.server_close()

def serve_background(port: int = DEFAULT_PORT, token: str | None = None,
                     allow_any_origin: bool = False):
    """在后台线程里启动代理，返回 (httpd, token, url)。供测试与嵌入式使用。"""
    llm = LLM()
    tok = token or secrets.token_urlsafe(16)
    handler = type("Handler", (_Handler,), {
        "llm": llm, "token": tok, "allow_any_origin": allow_any_origin,
    })
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=_serve_quietly, args=(httpd,), daemon=True)
    t.start()
    return httpd, tok, f"http://127.0.0.1:{port}"
