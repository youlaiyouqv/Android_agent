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
    # raise Exception("天气服务超时")
    fake_data = {"北京": "晴，22°C", "上海": "多云，26°C", "广州": "阴，28°C"}
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

# 系统提示词，给模型定人设和工作方式
SYSTEM_PROMPT = """你是一个可以使用工具的助手。
- 需要信息时就调用工具，可以分多次调用，直到信息足够回答用户。
- 每次调用工具前，先用一句话说明你为什么要调用它。
- 信息足够时，直接给出最终回答，不要再调用工具。"""


# 执行单个工具调用，并且处理所有可能出错的情况
def execute_tool(call):
    name = call.function.name

    # 情况1: 模型编造了一个不存在的工具名
    if name not in TOOL_FUNCS:
        return f"错误：没有名为{name}的工具。可用的工具有：{list(TOOL_FUNCS.keys())}"
    # 情况2: 模型给的参数不是合法的 JSON 如少了括号、引号
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        return f"错误：参数格式不是合法的JSON：{call.function.arguments}"
    # 情况3: 工具本身执行时出错，如参数名写错，网络超时
    try:
        return str(TOOL_FUNCS[name](**args))
    except Exception as e:
        return f"错误：工具执行失败：{e}"
    

    # agent主循环：ReAct的核心。ReAct = Reason思考 + Act行动：想一下 -> 做一下 -> 看结果 -> 再想
def run_agent(question, max_steps=10):
    messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    ]

    for step in range(1, max_steps + 1):
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools,
        )
        msg = resp.choices[0].message
        messages.append(msg)

        # 判断是否结束：模型不再调用工具，可以回答了
        if not msg.tool_calls:
            print(f"\n✅ 第{step}步：任务完成")
            return msg.content
        
        # 打印模型的思考（系统提示此要求它调用前说一句理由）
        if msg.content:
            print(f"\n🤔 第{step}步思考：{msg.content}")

        # 行动：执行这一步模型要求的所有工具
        for call in msg.tool_calls:
            result = execute_tool(call)
            print(f"🔨调用 {call.function.name}({call.function.arguments}) -> {result}")
            # 观察：结果塞回对话，下一轮模型就能看到
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })
        # 这一轮结束，回答for开头，让模型基于新结果继续思考
    # 走到这里说明循环跑满了还没结束
    return "⚠️ 超过最大步数，任务未完成"


# 程序入口
if __name__ == "__main__":
    answer = run_agent("现在几点了？如果现在是晚上，查一下广州天气，如果是上午，查北京天气。然后把温度*3")
    print("\n最终回答：", answer)