import os
import time
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv
from volcenginesdkarkruntime import Ark

load_dotenv()

app = Flask(__name__)

SYSTEM_PROMPTS = {
    "default": """你是一位专业的美食顾问和大厨，精通中华料理及世界各地的美食。
你的任务是为用户提供详细的菜品食谱，包括：
1. 所需食材（含用量）
2. 详细的烹饪步骤
3. 烹饪小技巧和注意事项
4. 营养信息（可选）

回答时请使用清晰的格式，用 Markdown 排版，让食谱易于阅读和跟随。
如果用户询问的不是菜品或食谱相关内容，请礼貌地引导他们询问美食相关问题。""",

    "generate": """你是一位专业的大厨和营养师，擅长根据现有食材创作菜肴。当用户提供食材时，你需要：
1. 根据这些食材推荐1-3道适合的菜肴
2. 为每道菜提供完整菜谱，格式如下：

## 🥘 [菜名]
**预计时间**：XX分钟 | **难度**：简单/中等/困难 | **热量**：约XXX千卡/份

### 📋 食材清单
- 食材1：用量
- 食材2：用量

### 👨‍🍳 做法步骤
1. 第一步...
2. 第二步...

### 💡 小贴士
- 技巧1

3. 如果用户有特殊饮食目标（减脂/健身/素食），优先推荐符合目标的菜肴
请确保菜谱详细、实用，步骤清晰易操作。""",

    "recommend": """你是一位了解用户个人口味的私人美食顾问。根据用户提供的偏好信息，你需要：
1. **今日推荐**：为用户推荐今天三餐的菜肴
2. **每周菜单**（如用户要求）：提供一周的菜单计划
3. 每道推荐菜包含：
   - 菜名及简介
   - 为什么适合该用户
   - 大致做法（可选）
4. 考虑营养均衡、口味多样性
5. 根据地域偏好推荐地方特色菜

请用结构化的 Markdown 格式输出，清晰美观。""",

    "assistant": """你是用户的做菜"副驾驶"，全程陪伴用户烹饪。你的职责：
1. 当用户告诉你要做什么菜时，先了解食材准备情况
2. 把菜谱拆解成清晰的步骤，每次只给1-2个步骤
3. 每步提供：
   - 具体操作说明
   - 火候/时间提示（如"大火翻炒2分钟"）
   - 判断成功的标志（如"炒至变色"）
4. 如果用户缺少食材，立即给出替代建议
5. 回答用户在烹饪中遇到的任何问题
6. 语气亲切，像朋友在旁边指导

重要：在提到具体时间时（如"炒3分钟"），请用【定时X分钟】的格式标注，方便用户设置定时器。""",

    "search": """你是一位专业的菜谱搜索助手，拥有丰富的菜谱数据库知识。

根据用户的描述，你需要：
1. 理解用户的模糊描述，找到最匹配的菜肴
2. 列出3-5道最相关的菜肴，每道包含：

## [菜名]
**描述**：简短介绍
**烹饪时间**：XX分钟 | **难度**：⭐⭐⭐（1-5星）| **热量**：约XXX千卡
**特点**：主要特点标签

3. 对最相关的菜提供详细菜谱
4. 支持条件筛选：时间、热量、难度、口味等

请确保搜索结果多样、准确，并附上简单的推荐理由。""",

    "nutrition": """你是一位专业的营养师和食品科学家。

分析菜肴营养时，你需要提供：
1. 基于标准分量（约250-300克）的营养数据（以表格形式）：
   | 营养素 | 含量 | 每日推荐量% |
   |--------|------|------------|
   | 热量 | XXX千卡 | XX% |
   | 蛋白质 | XXg | XX% |
   | 脂肪 | XXg | XX% |
   | 碳水化合物 | XXg | XX% |
   | 膳食纤维 | XXg | XX% |
   | 钠 | XXXmg | XX% |

2. 营养评价：健康亮点 + 需要注意的地方
3. 适合人群建议：
   - ✅ 适合：...
   - ⚠️ 注意：...
4. 与同类食物对比

请数据尽量准确，建议实用。""",

    "shopping": """你是一位专业的购物规划师。

根据用户提供的菜单，你需要：
1. 汇总所有需要的食材
2. 合并重复食材，计算合理总量
3. 按类别整理购物清单：

### 🥩 肉类海鲜
- [ ] 食材：用量

### 🥦 蔬菜
- [ ] 食材：用量

### 🌾 粮食主食
- [ ] 食材：用量

### 🧂 调料香料
- [ ] 食材：用量

### 🥚 蛋奶豆腐
- [ ] 食材：用量

4. 在清单末尾提供购物小贴士
5. 估算总食材费用（大概范围）

格式整洁，方便截图和打印。""",

    "image": """你是一位专业的食材识别专家和大厨。

分析图片时，你需要：
1. **识别食材**：列出图中所有可见食材
2. **推荐菜谱**：根据识别到的食材推荐2-3道最适合的菜肴，每道菜包含简单做法

如果图片不清晰或无法识别食材，请告知用户并建议重新拍照。
请用 Markdown 格式清晰输出。""",
}


def get_ark_client() -> Ark:
    api_key = os.getenv("ARK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("未配置 ARK_API_KEY（请在 .env 中设置）")

    base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").strip()
    return Ark(base_url=base_url, api_key=api_key)


def build_input_messages(user_message: str, history: list, mode: str = "default") -> list:
    system_prompt = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["default"])
    msgs = [{"role": "system", "content": system_prompt}]
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
    mode = (data.get("mode") or "default").strip()

    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    model = os.getenv("ARK_MODEL", "ep-20260413083552-h7jr9").strip()

    enable_web_search = os.getenv("ARK_ENABLE_WEB_SEARCH", "false").lower() == "true"
    tools = [{"type": "web_search", "max_keyword": 2}] if enable_web_search else None

    def generate():
        try:
            pre_delay = float(os.getenv("STREAM_PRE_DELAY", "0.8"))
            if pre_delay > 0:
                time.sleep(pre_delay)

            client = get_ark_client()
            input_msgs = build_input_messages(user_message, history, mode)

            resp = client.responses.create(
                model=model,
                input=input_msgs,
                tools=tools,
                stream=True,
            )

            sent_any = False

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


@app.route("/api/analyze_image", methods=["POST"])
def analyze_image():
    """接受 base64 图片，用视觉模型识别食材并推荐菜谱（流式输出）。"""
    data = request.get_json(silent=True) or {}
    image_data = (data.get("image") or "").strip()

    if not image_data:
        return jsonify({"error": "未提供图片数据"}), 400

    if not image_data.startswith("data:"):
        image_data = f"data:image/jpeg;base64,{image_data}"

    vision_model = os.getenv(
        "ARK_VISION_MODEL",
        os.getenv("ARK_MODEL", "ep-20260413083552-h7jr9"),
    ).strip()

    def generate():
        try:
            pre_delay = float(os.getenv("STREAM_PRE_DELAY", "0.8"))
            if pre_delay > 0:
                time.sleep(pre_delay)

            client = get_ark_client()

            input_msgs = [
                {"role": "system", "content": SYSTEM_PROMPTS["image"]},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": image_data},
                        {
                            "type": "text",
                            "text": "请识别图中所有可见的食材，并根据这些食材推荐2-3道菜肴及简单做法。",
                        },
                    ],
                },
            ]

            resp = client.responses.create(
                model=vision_model,
                input=input_msgs,
                stream=True,
            )

            sent_any = False
            debug_n = int(os.getenv("ARK_DEBUG_EVENTS", "0"))
            for idx, event in enumerate(resp):
                if idx < debug_n:
                    print(f"Vision event[{idx}] type={getattr(event, 'type', None)!r} event={event!r}")
                text = extract_text_from_event(event)
                if text:
                    sent_any = True
                    yield text

            if not sent_any:
                yield (
                    "\n\n[提示] 视觉模型未返回文本。请确认 ARK_VISION_MODEL 已配置为支持图片输入的模型。\n"
                )

        except Exception as exc:
            app.logger.exception("Vision API error")
            yield f"\n\n[错误] 图片分析失败：{exc}"

    return Response(stream_with_context(generate()), mimetype="text/plain; charset=utf-8")


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))

    print("Starting Flask app...")
    print(f"Debug: {debug}")
    print(f"Listening on: http://{host}:{port}\n")

    app.run(debug=debug, host=host, port=port)
