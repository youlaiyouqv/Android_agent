import os
import json
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com"
)

# 1 真正干活的函数（助理的技能）
def get_weather(city):
    fake_data = {"北京": "晴，22°C", "上海": "多云，26°C"}
    return fake_data.get(city, f"{city}: 暂无数据")

def calculator(expression):
    try:
        return str(eval(expression))
    except Exception as e:
        return f"计算出错：{e}"

def get_current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_city_population(city):
    fake_data = {"北京": "2180万"}
    return fake_data.get(city, f"{city}: 暂无统计")

# 工具名 -> 函数 的对照表，模型说调哪个名字，就从这里找对应的函数
TOOL_FUNCS = {
    "get_weather": get_weather,
    "calculator": calculator,
    "get_current_time": get_current_time,
    "get_city_population": get_city_population,
}

# 2 给模型看的工具说明书
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的当前天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "城市名，如：北京"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算一个数学表达式，例如 23*37",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "数学表达式"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "查询现在的时间",
            "parameters": {
                "type": "object",
                "properties": {}
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_city_population",
            "description": "查询指定城市的常住人口人数",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名，如北京",
                    }
                },
                "required": ["city"],
            },
        },
    },
]

# 3 第一次问模型
messages = [{"role": "user", "content": "现在几点？北京天气怎么样？顺便算一下23*47,北京的常住人口是多少"}]

resp = client.chat.completions.create(model="deepseek-chat", messages=messages, tools=tools)
msg = resp.choices[0].message
messages.append(msg)

# 4 助理逐个执行工具，把结果交回去
if msg.tool_calls:
    for call in msg.tool_calls:
        name = call.function.name
        args = json.loads(call.function.arguments)
        result = TOOL_FUNCS[name](**args)
        print(f"执行 {name}({args}) -> {result}")

        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": result,
        })

# 5 第二次问模型，让它看着结果作答
resp2 = client.chat.completions.create(model="deepseek-chat", messages=messages, tools=tools)
print("\n最终回答：", resp2.choices[0].message.content)