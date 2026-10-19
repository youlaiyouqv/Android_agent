# 手机操作Agent： 通过MCP调用android_server.py里的工具
# 本文件扮演两个角色：
# Host: 有大模型、有ReAct循环。 Client: 负责启动 MCP Server、获取工具、转发调用
import os
import sys
import json
import asyncio
from dotenv import load_dotenv
from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()
llm = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)

# 系统提示词：给Agent定工作方法。 直接影响成功率，下午修复失败时，它是最常改的地方之一
SYSTEM_PROMPT = """你是一个操作 Android 手机的助手，通过工具完成用户的任务。
工作方法：
1. 点击、输入、滑动、按键、打开应用之后，工具会自动返回操作后的屏幕，不需要再单独调用 get_screen_elements。
2. 常用应用包名：设置 com.android.settings，时钟 com.google.android.deskclock，通讯录 com.google.android.contacts，Chrome com.android.chrome。其他应用先用 find_app 查包名。
3. 屏幕上找不到目标时，先 swipe 滑动；滑动两次仍找不到，就用页面里的搜索功能。
4. 如果操作后屏幕没有变化，说明操作没生效，必须换一种方法，不要重复同一个操作。
5. 输入文字后如果键盘遮挡了需要点击的内容，先用 press_key("back") 收起键盘。
6. 元素后面的"已开启/已关闭""已选中/未选中"就是开关和选项的真实状态，回答状态类问题时以它为准。
7. 调节亮度、音量等滑块时，使用 tap_slider。
8. 宣布完成前，确认屏幕上已经出现完成的证据，并在回答中说明依据。
9. 不要为了确认状态去点击开关或修改设置，点击开关会改变它的状态。需要确认时，重新读取屏幕即可。
10. 需要输入文字时，先点击标有"输入框"的元素，再用 input_text 输入。
11. 如果确认无法完成，说明原因后结束。
12. 用中文思考和回答。"""

def to_openai_tools(mcp_tools):
    """把MCP的工具格式，转换成大模型API要求的tools格式
    这就是Client的"翻译"工作：Server 说 MCP 的话，模型 API 说 OpenAI 的话
    还记得前面手写的 tools 说明书吗？现在它是从 Server 自动拿到再自动转换的"""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema,
            },
        }
        for t in mcp_tools
    ]


# async def: 异步函数。MCP的SDK是异步写的，所以这里要用async
# 只需要知道：调用Server的地方前面要加await, 意思即是等Server回复
async def run_agent(question, max_steps=30):

    # 告诉Client怎么启动Server： 用当前python去运行android_server.py
    # sys.executable 就是当前正在运行的python（venv里的那个），避免找错环境
    server_params = StdioServerParameters(
        command=sys.executable, 
        args=["android_server.py"],
    )

    # async with: 建立连接，代码块结束时自动断开、自动关掉Server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 问Server：你有哪些工具？
            tool_list = await session.list_tools()
            tools = to_openai_tools(tool_list.tools)
            print(f"已连接 MCP Server，获取到 {len(tools)} 个工具\n")

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ]

            total_tokens = 0
            # 下面就是之前写过的ReAct循环，结构一样
            for step in range(1, max_steps + 1):
                resp = llm.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages,
                    tools=tools,
                    temperature=0,
                )
                total_tokens += resp.usage.total_tokens
                msg = resp.choices[0].message
                messages.append(msg)

                # 模型不再调用工具 -> 结束
                if not msg.tool_calls:
                    return msg.content, step, total_tokens

                if msg.content:
                    print(f"🤔第 {step} 步思考：{msg.content}")

                # 行动 + 观察
                for call in msg.tool_calls:
                    try:
                        args = json.loads(call.function.arguments or "{}")
                        # 唯一的变化在此处：不再直接调用本地函数，而是通过 MCP 让 Server 执行
                        result = await session.call_tool(call.function.name, args)
                        # Server 返回的内容是一个列表，把其中的文字拼起来
                        text = "\n".join(c.text for c in result.content if hasattr(c, "text"))
                        if result.isError:
                            text = "错误：" + text
                    except json.JSONDecodeError:
                        text = f"错误：参数不是合法的 JSON：{call.function.arguments}"
                    except Exception as e:
                        text = f"错误：{e}"

                    # 屏幕元素列表可能很长，打印时只显示前 200 个字，但完整内容会发给模型
                    preview = text if len(text) <= 3000 else text[:3000] + "......"
                    print(f"🪛第 {step} 步：{call.function.name}({call.function.arguments}) -> {preview}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": text,
                    })

            return "⚠️超过最大步数，任务未完成", max_steps, total_tokens


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "打开设置，告诉我Android版本号"
    answer, steps, tokens = asyncio.run(run_agent(question))
    print(f"\n✅共 {steps} 步, 消耗 {tokens} tokens")
    print(f"最终回答：{answer}")