import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)

# 1. 告诉模型：你有哪些工具可以用
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的当前天气",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名，如：北京"}
                },
                "required": ["city"],
            },
        },
    }
]

# 2. 带着工具清单去提问
resp = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "北京今天天气怎么样？"}],
    tools=tools,
)

msg = resp.choices[0].message
print("模型的文字回复:", msg.content)
print("模型想调用的工具:", msg.tool_calls)

# 3. 把工具调用拆开看
if msg.tool_calls:
    call = msg.tool_calls[0]
    print("工具名:", call.function.name)
    print("参数:", json.loads(call.function.arguments))