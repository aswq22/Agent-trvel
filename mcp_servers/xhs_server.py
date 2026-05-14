# mcp_servers/xhs_server.py
# 小红书旅游攻略 MCP Server
# 提供 xhs_search_notes / xhs_get_note 两个工具
# 有 XHS_COOKIE 时走真实抓取，否则返回 Mock 数据供测试
import hashlib
import json
from typing import Optional

import httpx
from fastmcp import FastMCP

from app.config import config

mcp = FastMCP("XHS")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.xiaohongshu.com/",
}

# ── Mock 数据（无 Cookie 时降级）────────────────────────────────────────────

_MOCK_NOTES = [
    {
        "note_id": "mock001",
        "title": "成都5天4夜深度游攻略｜必去景点+美食推荐",
        "content": (
            "成都是一座来了就不想离开的城市。推荐行程：\n"
            "第1天：宽窄巷子→锦里→春熙路。宽窄巷子保留了大量清代建筑，晚上在锦里吃串串。\n"
            "第2天：大熊猫繁育研究基地（7:30前到门口排队），下午都江堰水利工程，建议半天。\n"
            "第3天：青城山，分前山（道教文化）和后山（原始景观），全程约5小时。\n"
            "第4天：乐山大佛，从成都出发高铁40分钟，船票提前购买，正面仰视震撼感超强。\n"
            "第5天：武侯祠+杜甫草堂，收尾完美。\n"
            "美食必吃：郫县豆瓣鱼、夫妻肺片、龙抄手、担担面、钟水饺、赖汤圆。\n"
            "住宿推荐：春熙路IFS附近，交通最便利，人均200-400元/晚。\n"
            "交通：地铁超方便，市内无需打车，景区间建议高铁+景区大巴。"
        ),
        "tags": ["成都", "旅游攻略", "四川", "美食", "熊猫"],
        "city": "成都",
        "author": "旅行达人小王",
        "url": "https://www.xiaohongshu.com/explore/mock001",
        "likes": 8832,
    },
    {
        "note_id": "mock002",
        "title": "北京故宫+胡同骑行3日游，超详细路线",
        "content": (
            "北京必游景点及实用tips：\n"
            "故宫：建议工作日早8:30前入园，人少；午门→太和殿→珍宝馆→御花园约4小时。"
            "预约票要提前2周抢，旺季1个月。\n"
            "颐和园：建议半天，乘船游昆明湖15元，长廊全长728米必走。\n"
            "天坛：上午光线最好，祈年殿金顶在阳光下非常漂亮，回音壁有趣可体验。\n"
            "胡同骑行：南锣鼓巷→什刹海→烟袋斜街，租自行车约20元/小时。\n"
            "长城：推荐慕田峪（人少风景好）或箭扣（驴友专线），避开八达岭旺季。\n"
            "美食：烤鸭首选大董或四季民福，炸酱面推荐老北京炸酱面，豆汁焦圈配套吃。\n"
            "住宿：东城区（故宫附近）或西城区，地铁2号线沿线最方便。"
        ),
        "tags": ["北京", "故宫", "胡同", "长城", "旅游攻略"],
        "city": "北京",
        "author": "首都玩家",
        "url": "https://www.xiaohongshu.com/explore/mock002",
        "likes": 6541,
    },
    {
        "note_id": "mock003",
        "title": "深圳南山区一日游完美路线，本地人带你玩",
        "content": (
            "南山区精华一日游：\n"
            "上午：华侨城欢乐谷或世界之窗（二选一），开门前到可省去排队时间。\n"
            "午餐：华侨城创意文化园OCT LOFT，众多网红餐厅，推荐COCO Park附近烧烤。\n"
            "下午：蛇口渔人码头→海上世界，可乘渡轮去珠海（约70分钟），适合跨城一日游。\n"
            "傍晚：深圳湾公园，夕阳下的跨海大桥极美，免费开放。\n"
            "夜晚：深圳湾万象城购物，或前海自贸区夜景打卡。\n"
            "交通：地铁2号线+9号线覆盖全区，打车备用。\n"
            "周边延伸：大梅沙/小梅沙海滩（东部），较场尾民宿海景（惠州方向）。"
        ),
        "tags": ["深圳", "南山", "本地生活", "一日游"],
        "city": "深圳",
        "author": "南山居民",
        "url": "https://www.xiaohongshu.com/explore/mock003",
        "likes": 3201,
    },
]


def _mock_search(keyword: str, city: str, count: int) -> list[dict]:
    results = []
    for note in _MOCK_NOTES:
        if (city.lower() in note["city"].lower() or
                city.lower() in note["title"].lower() or
                any(city.lower() in t.lower() for t in note["tags"]) or
                keyword.lower() in note["title"].lower() or
                keyword.lower() in note["content"].lower()):
            results.append(note)
    return results[:count] if results else _MOCK_NOTES[:count]


# ── 真实抓取（需配置 XHS_COOKIE）───────────────────────────────────────────

async def _real_search(keyword: str, city: str, count: int) -> list[dict]:
    """调用小红书搜索接口（需要有效 Cookie）"""
    headers = {**_HEADERS, "Cookie": config.xhs_cookie}
    params = {
        "keyword": f"{city} {keyword}".strip(),
        "page": 1,
        "page_size": min(count, 20),
        "sort": "general",
        "note_type": 0,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    notes = []
    for item in data.get("data", {}).get("items", []):
        note = item.get("note_card", {})
        note_id = item.get("id", "")
        title = note.get("title", "") or note.get("desc", "")[:50]
        content = note.get("desc", "")
        tag_list = [t.get("name", "") for t in note.get("tag_list", [])]
        notes.append({
            "note_id": note_id,
            "title": title,
            "content": content,
            "tags": tag_list,
            "city": city,
            "author": note.get("user", {}).get("nickname", ""),
            "url": f"https://www.xiaohongshu.com/explore/{note_id}",
            "likes": note.get("interact_info", {}).get("liked_count", 0),
        })
    return notes


@mcp.tool()
async def xhs_search_notes(
    keyword: str,
    city: str = "",
    count: int = 5,
) -> dict:
    """搜索小红书旅游攻略笔记

    Args:
        keyword: 搜索关键词，如 "旅游攻略"、"美食推荐"
        city: 城市名，如 "成都"、"北京"，可为空
        count: 返回笔记数量，默认 5

    Returns:
        包含笔记列表的字典，每条笔记含 title / content / tags / url
    """
    try:
        if config.xhs_cookie:
            notes = await _real_search(keyword, city, count)
        else:
            notes = _mock_search(keyword, city, count)

        return {
            "status": "success",
            "source": "realtime" if config.xhs_cookie else "mock",
            "keyword": keyword,
            "city": city,
            "total": len(notes),
            "notes": notes,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "notes": []}


@mcp.tool()
async def xhs_get_note(note_id: str) -> dict:
    """获取小红书笔记详情

    Args:
        note_id: 笔记 ID（从 xhs_search_notes 结果中获取）

    Returns:
        笔记详细内容
    """
    # Mock 数据查找
    for note in _MOCK_NOTES:
        if note["note_id"] == note_id:
            return {"status": "success", "note": note}

    if not config.xhs_cookie:
        return {"status": "error", "error": "未配置 XHS_COOKIE，无法获取真实内容"}

    headers = {**_HEADERS, "Cookie": config.xhs_cookie}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"https://www.xiaohongshu.com/explore/{note_id}",
            headers=headers,
        )
        resp.raise_for_status()

    return {"status": "success", "note": {"note_id": note_id, "content": resp.text[:3000]}}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8013)
