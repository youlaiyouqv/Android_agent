# Android设备操作MCP Server
# 把 adb 能力封装成MCP工具，供 Agent 调用
import re
import time 
import subprocess
import xml.etree.ElementTree as ET
import uiautomator2 as u2
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("android-tools")

# 记住上一次读取到的屏幕元素。模型只会说“点第5号”，工具需要从这里查出第5号的坐标
_last_elements = []
_device = None

_screen_h = None

IME_PACKAGES = {"com.google.android.inputmethod.latin"}

# 内部辅助函数，没有@mcp.tool(), 不暴露给模型
def adb(*args):
    """执行一条adb命令，返回输出文本，失败时抛出异常"""
    result = subprocess.run(
        ["adb", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "adb命令执行失败")
    return result.stdout

def _center(bounds):
    """把"[0,210][1080,399]"这样的区域，换算成中心点坐标"""
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", bounds))
    return (x1 + x2) // 2, (y1 + y2) // 2


def _screen_height():
    """屏幕高度，只查一次"""
    global _screen_h
    if _screen_h is None:
        _screen_h = _screen_size()[1]
    return _screen_h

def _get_device():
    """连接设备，只连一次，后面重复使用"""
    global _device
    if _device is None:
        _device = u2.connect()
    return _device

def _dump_ui(retries=3):
    """用 uiautomator2 导出界面XML，不受'界面不静止'影响；失败就报错，绝不返回旧画面"""
    last_err = None
    for _ in range(retries):
        try:
            xml_text = _get_device().dump_hierarchy()
            if xml_text.strip():
                return xml_text
        except Exception as e:
            last_err = e
        time.sleep()
    raise RuntimeError(f"读取屏幕失败(已重试{retries}次: {last_err})")

def _parse_bounds(bounds):
    """把"[0,210][1080,399]"转成(0, 210, 1080, 399); 格式不对或面积为0时返回None"""
    nums = list(map(int, re.findall(r"\d+", bounds or "")))
    if len(nums) != 4:
        return None
    x1, y1, x2, y2 = nums
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2 

def _screen_size():
    """读取屏幕分辨率，滑动时用"""
    out = adb("shell", "wm", "size")
    w, h = re.findall(r"(\d+)x(\d+)", out)[-1]
    return int(w), int(h)

def _get_element(index):
    """按编号取元素，同时做合法性检查。返回（元素，错误信息）"""
    if not _last_elements:
        return None, "错误：请先调用 get_screen_elements 读取屏幕"
    if index < 0 or index >= len(_last_elements):
        return None, f"错误：编号{index}不存在，有效范围是 0 到 {len(_last_elements) - 1}"
    return _last_elements[index], None

def _with_screen(message):
    """操作完成后，自动附上最新的屏幕内容
    为什么：以前每次操作后模型都要再调一次 get_screen_elements, 步数和token都翻倍"""
    try:
        screen = get_screen_elements()
    except Exception as e:
        screen = f"（读取屏幕失败：{e}）"
    return f"{message}\n\n操作后的屏幕：\n{screen}"

@mcp.tool()
def get_screen_elements() -> str:
    """读取当前屏幕上的界面元素，返回编号和文字和状态。
    任务开始时调用一次即可；点击、输入、滑动、按键、打开应用后会自动返回新屏幕，无需重复调用。"""
    global _last_elements
    root = ET.fromstring(_dump_ui())

    parent_of = {child: parent for parent in root.iter() for child in parent}

    def clickable_ancestor(node):
        """从当前节点往上找，返回第一个可点击的节点（包括自己）"""
        cur = node
        while cur is not None:
            if cur.get("clickable") == "true":
                return cur
            cur = parent_of.get(cur)
        return None

    def row_text(node):
        """找到开关所在那一行的文字，比如Dark theme, 用来给没文字的开关命名"""
        anc = clickable_ancestor(node)
        if anc is None:
            return None
        for d in anc.iter("node"):
            t = d.get("text") or d.get("content-desc")
            if t:
                return t
        return None

    elements, lines = [], []
    for node in root.iter("node"):
        if node.get("package") in IME_PACKAGES:
            continue
        own = _parse_bounds(node.get("bounds"))
        if own is None:
            continue

        if node.get("package") == "com.android.systemui" and own[3] <= _screen_height() * 0.06:
            continue

        text = node.get("text") or node.get("content-desc")
        rid = node.get("resource-id", "").split("/")[-1]
        cls = node.get("class", "")
        is_slider = "SeekBar" in cls  #滑块：亮度、音量等
        is_checkable = node.get("checkable") == "true"  #开关、单选、复选
        is_input = "EditText" in cls
        

        # 过滤噪音：有文字的保留；没文字但可点击的用资源 id 命名；
        # 既没文字又不可点击的（content、launcher、app_bar 这类布局容器）直接丢掉
        if text:
            label = text
        elif is_input:
            label = rid or "输入框"
        elif is_slider:
            label = rid or "滑块"
        elif is_checkable:
            label = f"{row_text(node) or rid or '某项'}的开关"
        elif node.get("clickable") == "true" and rid: 
            label = rid
        else:
            continue

        # 点击坐标：优先用最近的可点击父节点（整行）的中心，而不是文字本身的中心
        anc = clickable_ancestor(node)
        target = _parse_bounds(anc.get("bounds")) if anc is not None else None
        tx1, ty1, tx2, ty2 = target or own


        tags = []
        if anc is not None:
            tags.append("可点击")
        if is_input:
            tags.append("输入框")
        if is_checkable:
            checked = node.get("checked") == "true"     # 属性是字符串，必须和 "true" 比较
            if "RadioButton" in cls:
                tags.append("已选中" if checked else "未选中")
            else:
                tags.append("已开启" if checked else "已关闭")
        if is_slider:
            tags.append("滑块，用 tap_slider 调节")

        

        elements.append({
            "label": label,
            "x": (tx1 + tx2) // 2,
            "y": (ty1 + ty2) // 2,
            "bounds": own,
            "slider": is_slider,
        })
        tag_str = f"（{','.join(tags)}）" if tags else ""
        lines.append(f"[{len(elements) - 1}] {label}{tag_str}")

    _last_elements = elements
    return "\n".join(lines) if lines else "屏幕上没有识别到元素"


@mcp.tool()
def tap_element(index: int) -> str:
    """点击屏幕元素。index是get_screen_elements返回的编号。
    执行后自动返回新屏幕"""
    e, err = _get_element(index)
    if err:
        return err
    adb("shell", "input", "tap", str(e["x"]), str(e["y"]))
    time.sleep(1)
    return _with_screen(f"已点击 [{index}] {e['label']}")

@mcp.tool()
def tap_slider(index: int, percent: int) -> str:
    """把滑块（如亮度、音量）调到指定位置。index是滑块的编号；
    percent 取 0-100，0为最小，100为最大，执行后自动返回新屏幕"""
    e, err = _get_element(index)
    if err:
        return err
    if not e["slider"]:
        return f"错误：[{index}] {e['label']} 不是滑块"
    x1, y1, x2, y2 = e["bounds"]
    p = max(0, min(100, percent))
    x = x1 + (x2 - x1) * p // 100
    x = max(x1 +3, min(x, x2 - 3)) #留一点边距，避免点到滑块外面
    y = (y1 + y2) // 2
    adb("shell", "input", "tap", str(x), str(y))
    time.sleep(1)
    return _with_screen(f"已将 [{index}] {e['label']} 调到 {p}%")    

@mcp.tool()
def input_text(text: str) -> str:
    """在当前选中的输入框中输入文字，只支持英文、数字和空格。"""
    if not text.isascii():
        return "错误：暂不支持输入中文，请改用英文或数字"
    adb("shell", "input", "text", text.replace(" ", "%s"))
    time.sleep(0.5)
    return f"已输入：{text}"

@mcp.tool()
def swipe(direction: str) -> str:
    """滑动屏幕。direction为up(向上滑，查看下方更多内容)或down(向下滑，回到上方)。"""
    w, h = _screen_size()
    x = w // 2
    if direction == "up":
        adb("shell", "input", "swipe", str(x), str(h * 3 // 4), str(x), str(h // 4), "300")
    elif direction == "down":
        adb("shell", "input", "swipe", str(x), str(h // 4), str(x), str(h * 3 // 4), "300")
    else:
        return "错误：direction只能是up或down"
    time.sleep(1)
    return _with_screen(f"已向{direction}滑动")

@mcp.tool()
def press_key(key: str) -> str:
    """按下系统按键，key为back(返回)、home(回到桌面)或enter(回车)。"""
    codes = {"back": 4, "home": 3, "enter": 66}
    if key not in codes:
        return f"错误：不支持的按键{key}, 可用：{list(codes)}"
    adb("shell", "input", "keyevent", str(codes[key]))
    time.sleep(1)
    return f"已按下{key}"

@mcp.tool()
def find_app(keyword: str) -> str:
    """按关键词查找已安装应用的包名，例如keyword=calculator。打开应用前先用它找到准确包名。"""
    out = adb("shell", "pm", "list", "packages")
    pkgs = [line.replace("package:", "") for line in out.splitlines()
            if keyword.lower() in line.lower()]
    return "\n".join(pkgs[:10]) if pkgs else f"没有找到包含{keyword}的应用"

@mcp.tool()
def open_app(package: str) -> str:
    """打开应用。packagege是包名，例如设置是com.android.settings。执行后自动返回新屏幕"""
    installed = adb("shell", "pm", "list", "packages", package).split()
    if f"package:{package}" not in installed:
        return f"错误：设备上没有安装 {package}, 请用find_app查找正确的包名"
    adb("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(2)
    return _with_screen(f"已打开{package}")


if __name__ == "__main__":
    mcp.run()