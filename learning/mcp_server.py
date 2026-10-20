from datetime import datetime
from mcp.server.fastmcp import FastMCP

# 创建一个MCP Server对象
mcp = FastMCP("demo-tools")

# 注册工具
@mcp.tool()
def get_weather(city: str) -> str:
    """查询指定城市的当前天气。参数city是城市名，如：北京"""
    fake_data = {"北京": "晴，22°C", "上海": "多云，26°C", "广州": "雷阵雨，31°C"}
    return fake_data.get(city, f"{city}: 暂无数据")

@mcp.tool()
def calculator(expression: str) -> str:
    """计算一个数学表达式，例如23*47"""
    try:
        return str(eval(expression))
    except Exception as e:
        return f"计算出错：{e}"

@mcp.tool()
def get_current_time() -> str:
    """获取当前的日期和时间"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 启动Server
if __name__ == "__main__":
    mcp.run()