import os
import time
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv
from volcenginesdkarkruntime import Ark

load_dotenv()

app = Flask(__name__)

SYSTEM_PROMPT = """你是一位专业的美食顾问和大厨，精通中华料理及世界各地的美食。
你的任务是为用户提供详细的菜品食谱，包括：
1. 所需食材（含用量）
2. 详细的烹饪步骤
3. 烹饪小技巧和注意事项
4. 营养信息（可选）

回答时请使用清晰的格式，用 Markdown 排版，让食谱易于阅读和跟随。
如果用户询问的不是菜品或食谱相关内容，请礼貌地引导他们询问美食相关问题。"""


def get_ark_client() -> Ark:
    api_key = os.getenv("ARK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("未配置 ARK_API_KEY（请在 .env 中设置）")

    base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").strip()
    return Ark(base_url=base_url, api_key=api_key)


def build_input_messages(user_message: str, history: list) -> list:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history or []:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": user_message})
    return msgs


def extract_text_from_event(event) -> str | None:
    """
    Ark Responses streaming 事件中，不同 event.type 的结构不同。
    这里先走“容错解析”：
    - 如果是 dict：递归找常见字段 text/content/delta/output_text
    - 如果是对象：优先看 __dict__ 再递归
    """
    def _extract(obj):
        if obj is None:
            return None
        if isinstance(obj, str):
            return None
        if isinstance(obj, dict):
            # 常见字段优先
            for k in ("output_text", "text", "content", "delta"):
                v = obj.get(k)
                if isinstance(v, str) and v.strip():
                    return v
            for v in obj.values():
                t = _extract(v)
                if t:
                    return t
            return None
        if isinstance(obj, list):
            for it in obj:
                t = _extract(it)
                if t:
                    return t
            return None

        # 对象属性（有些 SDK 用对象）
        for attr in ("output_text", "text", "content", "delta"):
            if hasattr(obj, attr):
                v = getattr(obj, attr)
                if isinstance(v, str) and v.strip():
                    return v

        d = getattr(obj, "__dict__", None)
        if isinstance(d, dict):
            return _extract(d)

        return None

    etype = getattr(event, "type", "") or ""
    # 只输出增量事件，避免最后的“完整文本”事件再输出一遍
    if isinstance(etype, str) and ("delta" in etype):
        return _extract(event)
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()
    history = data.get("history") or []

    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    model = os.getenv("ARK_MODEL", "ep-20260413083552-h7jr9").strip()

    enable_web_search = os.getenv("ARK_ENABLE_WEB_SEARCH", "false").lower() == "true"
    tools = [{"type": "web_search", "max_keyword": 2}] if enable_web_search else None

    def generate():
        try:
            # 模拟“先加载一会儿”
            pre_delay = float(os.getenv("STREAM_PRE_DELAY", "0.8"))
            if pre_delay > 0:
                time.sleep(pre_delay)

            client = get_ark_client()
            input_msgs = build_input_messages(user_message, history)

            resp = client.responses.create(
                model=model,
                input=input_msgs,
                tools=tools,
                stream=True,
            )

            sent_any = False

            # 打印前 12 个 event，方便你后续精确适配（要关掉就改成 0）
            debug_n = int(os.getenv("ARK_DEBUG_EVENTS", "0"))
            for idx, event in enumerate(resp):
                if idx < debug_n:
                    print(f"Ark event[{idx}] type={getattr(event, 'type', None)!r} event={event!r}")

                text = extract_text_from_event(event)
                if text:
                    sent_any = True
                    yield text

            if not sent_any:
                yield (
                    "\n\n[提示] 火山引擎返回了流式响应，但没有解析到文本字段。\n"
                    "你可以在 .env 设置 ARK_DEBUG_EVENTS=30，然后把控制台里出现 delta/text 的事件贴出来，我帮你把解析写成精确版。\n"
                )

        except Exception as exc:
            app.logger.exception("Ark API error")
            yield f"\n\n[错误] Ark 调用失败：{exc}"

    return Response(stream_with_context(generate()), mimetype="text/plain; charset=utf-8")


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))

    print("Starting Flask app...")
    print(f"Debug: {debug}")
    print(f"Listening on: http://{host}:{port}\n")

    app.run(debug=debug, host=host, port=port)