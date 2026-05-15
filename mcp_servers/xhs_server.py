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


# ── 真实抓取：Playwright + DOM 解析（避开 X-S 签名逆向）─────────────────────
#
# 设计：进程启动时不立即拉起 chromium；首个真实 search 请求到达时懒加载，
# 之后复用同一个 browser context（cookie + 状态保留，省 chromium 启动开销）。

_pw_state: dict = {"playwright": None, "browser": None, "context": None}


def _parse_cookie_str(s: str) -> list[dict]:
    """把 'a=1; b=2; ...' 形式的 cookie 字符串拆成 Playwright add_cookies 需要的列表。"""
    cookies: list[dict] = []
    for kv in s.split(";"):
        kv = kv.strip()
        if "=" not in kv:
            continue
        name, _, value = kv.partition("=")
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": ".xiaohongshu.com",
            "path": "/",
        })
    return cookies


async def _get_context():
    """懒加载并复用同一个 chromium context。"""
    if _pw_state["context"] is not None:
        return _pw_state["context"]
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent=_HEADERS["User-Agent"],
        locale="zh-CN",
        viewport={"width": 1280, "height": 900},
    )
    if config.xhs_cookie:
        await context.add_cookies(_parse_cookie_str(config.xhs_cookie))
    _pw_state["playwright"] = pw
    _pw_state["browser"] = browser
    _pw_state["context"] = context
    return context


async def _real_search(keyword: str, city: str, count: int) -> list[dict]:
    """用 Playwright 打开 XHS 搜索结果页，解析 DOM 抽笔记列表。

    比逆向 X-S 签名简单很多，代价是每条请求 ~5-10s。
    """
    from urllib.parse import quote

    ctx = await _get_context()
    page = await ctx.new_page()
    full_keyword = f"{city} {keyword}".strip()
    url = f"https://www.xiaohongshu.com/search_result?keyword={quote(full_keyword)}&source=web_explore_feed"

    notes: list[dict] = []
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # 等笔记卡片渲染——多个 selector 任一命中即可
        selectors = [
            "section.note-item",
            "a[href*='/explore/']",
            "a[href*='/discovery/item/']",
            "a[href*='/search_result/']",
        ]
        matched_selector = None
        for sel in selectors:
            try:
                await page.wait_for_selector(sel, timeout=4000)
                matched_selector = sel
                break
            except Exception:
                continue

        if matched_selector is None:
            # 一个都没等到 —— 把现场存下来供调试
            import os as _os
            dbg_dir = _os.path.dirname(_os.path.abspath(__file__))
            png_path = _os.path.join(dbg_dir, "xhs_debug.png")
            html_path = _os.path.join(dbg_dir, "xhs_debug.html")
            try:
                await page.screenshot(path=png_path, full_page=True)
                html = await page.content()
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html)
                hint = ""
                if "登录" in html: hint = "（页面含'登录'字样，cookie 可能失效）"
                elif "验证" in html: hint = "（页面含'验证'字样，被风控）"
                elif "<title>404" in html or "404 Not Found" in html: hint = "（404 — URL 不对？）"
                raise RuntimeError(
                    f"XHS 页面未渲染出笔记卡片{hint}。已存截图 {png_path} 和 HTML {html_path}"
                )
            except Exception as e:
                if "XHS 页面未渲染出" in str(e):
                    raise
                raise RuntimeError(f"XHS 页面调试 dump 失败: {e}")

        # 给懒加载几百毫秒
        await page.wait_for_timeout(800)

        # 抓所有指向笔记详情的链接（兼容多种 URL 结构）
        anchors = await page.locator(
            "a[href*='/explore/'], a[href*='/discovery/item/'], a[href*='/search_result/']"
        ).all()
        seen_ids: set[str] = set()
        for a in anchors:
            if len(notes) >= count:
                break
            href = await a.get_attribute("href")
            if not href:
                continue
            # 形如 /explore/64abcde123456789?xsec_token=...
            note_id = href.split("/explore/")[-1].split("?")[0].strip()
            if not note_id or note_id in seen_ids:
                continue
            # title: 链接的 title 属性 / 内部文本 / 父节点文本
            title = (await a.get_attribute("title")) or ""
            if not title:
                title = (await a.text_content() or "").strip()
            # author / likes 从卡片附近抽（XHS 的卡片结构 = section.note-item 包 a + 作者 + 互动信息）
            try:
                card = a.locator("xpath=ancestor::section[1]")
                author = ""
                try:
                    author_el = card.locator(".author").first
                    author = (await author_el.text_content() or "").strip()
                except Exception:
                    pass
                likes = 0
                try:
                    likes_text = (await card.locator(".count").first.text_content() or "").strip()
                    # XHS 显示如 '1.2万'、'234'，做近似解析
                    if "万" in likes_text:
                        likes = int(float(likes_text.replace("万", "")) * 10000)
                    elif likes_text.isdigit():
                        likes = int(likes_text)
                except Exception:
                    pass
            except Exception:
                author = ""
                likes = 0

            if not title:
                continue  # 没标题的卡片跳过

            seen_ids.add(note_id)
            notes.append({
                "note_id": note_id,
                "title": title[:80],
                # content：列表页拿不到完整正文，先用 title 占位；下一步可进详情页拉
                "content": title,
                "tags": [city] if city else [],
                "city": city,
                "author": author,
                "url": f"https://www.xiaohongshu.com{href.split('?')[0]}",
                "likes": likes,
            })
    finally:
        await page.close()

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
