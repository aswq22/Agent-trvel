# 小红书 RAG 前端集成 — 设计文档

- **日期**：2026-05-14
- **状态**：设计已批准，待生成实施计划
- **关联后端**：`docs/superpowers/specs/2026-05-14-xhs-rag-dynamic-kb-design.md`（已实现并合入 `feat/xhs-rag` 分支）

## 1. 目标与非目标

### 目标

1. 用户在现有聊天 UI 中**手动**选择是否走 RAG（沿用后端"手动开关"决策）
2. 提供 KB 的搜索入库 / 列表浏览 / 切换 / 删除的可视化交互
3. RAG 回答时引用来源（小红书笔记 title/url/author/likes）可见、可点
4. 不破坏现有「聊天 / 旅游规划」双 App Mode 与「快速 / 流式」子模式

### 非目标

- 引入前端测试框架（Jest/Vitest）—— YAGNI，纯手测
- 主题切换（深色模式等）
- 真实小红书 cookie 抓取的稳定性（沿用后端 mock fallback）
- KB > 50 时的虚拟滚动 / LRU
- 移动端真机适配（只做 Chrome DevTools 窄屏模拟）

## 2. 用户决策（已对齐）

| 维度 | 决策 |
|---|---|
| 入口形式 | 作为聊天子模式（**快速 / 流式 / RAG** 三选一） |
| KB 管理入口 | RAG 子模式下 KB 选择条上的 [管理] 按钮 |
| 管理面板形式 | **右侧抽屉**，宽 420px |
| 管理面板功能 | 搜索入库表单 + KB 列表 + 删除二次确认（不要手动粘贴入库） |
| 引用展示 | 消息**上方**可折叠"📕 基于 N 条小红书攻略" |
| 无 KB 状态 | 点发送 → KB bar 红色 shake + 自动弹开抽屉 |
| 会话切换 | 历史保留，上下文连续（沿用后端 session_store） |

## 3. 总体布局

```
┌─ 侧边栏（现有，不改）┐┌──────────── 主区域 ────────────────────┐
│ [新建对话]            ││ 💬 聊天模式                            │
│ ● 聊天                ││                                        │
│ ○ 旅游规划            ││ ┌─ Assistant 消息 ───────────────────┐│
│ 近期对话              ││ │ ▶ 📕 基于 3 条小红书攻略           ││
└──────────────────────┘│ │ ───────────────────────────────────││
                        │ │ 根据小红书攻略，成都必吃的有…       ││
                        │ └────────────────────────────────────┘│
                        │                                        │
                        │ ┌─ KB 选择条 (仅 RAG 子模式可见) ──┐  │
                        │ │ 📕 知识库: ┊成都美食▾┊ [管理 +]   │  │
                        │ └─────────────────────────────────┘  │
                        │ ┌─ 输入框（现有） ──────────────────┐│
                        │ │ 问我点啥...                       ││
                        │ │ [···]            [RAG ▾] [↑]      ││
                        │ └───────────────────────────────────┘│
                        └──────────────────────────────────────┘

                                  ┌─ 右侧抽屉 ────────────┐
                                  │ 📕 小红书知识库   [×] │
                                  │ ▼ 搜索并入库          │
                                  │  关键词 [___]         │
                                  │  城市   [___]         │
                                  │  数量   [5▾]          │
                                  │  [搜索并入库]         │
                                  │ ▼ 我的知识库 (3) ⟳    │
                                  │  ┌──────────────────┐│
                                  │  │● 美食|成都       ││
                                  │  │ 47 块 · 15:30 🗑 ││
                                  │  └──────────────────┘│
                                  │  ...                  │
                                  └──────────────────────┘
```

### 状态机

```ts
sub_mode:              'quick' | 'stream' | 'rag'
kb.selectedName:       string | null     // 持久化到 localStorage('xhs_selected_kb')
kb.list:               KbItem[]          // 抽屉首次开时拉
kb.loaded:             boolean
kb.drawerOpen:         boolean
kb.pendingSendAfterSelect: boolean       // 无 KB 点发送 → 缓存待续发
kb.pendingQuestion:    string
```

## 4. DOM 改动（`static/index.html`）

### 4.1 子模式下拉新增 RAG 项

在 `#modeDropdown` 内追加：

```html
<div class="dropdown-item" data-mode="rag">
    <div class="dropdown-item-main"><span>RAG · 小红书</span></div>
    <div class="dropdown-item-sub">基于小红书攻略检索</div>
</div>
```

`#currentModeText` 显示规则：`{quick:'快速', stream:'流式', rag:'RAG'}`。

### 4.2 KB 选择条（输入框上方）

插入到 `.chat-input-container` 内、`.input-group-wrapper` 之前：

```html
<div class="kb-bar" id="kbBar" style="display:none">
    <span class="kb-bar-icon">📕</span>
    <span class="kb-bar-label">知识库:</span>
    <button class="kb-bar-select" id="kbBarSelect">
        <span id="kbBarSelectedName" class="kb-bar-placeholder">请选择知识库</span>
        <svg class="dropdown-arrow"><!-- 下拉箭头 --></svg>
    </button>
    <div class="kb-bar-spacer"></div>
    <button class="kb-bar-manage" id="kbBarManageBtn">
        <svg width="14" height="14"><!-- + 图标 --></svg>
        <span>管理</span>
    </button>
</div>
```

v1 简化：`#kbBarSelect` 点击直接打开抽屉（不做"小型下拉浮层"，YAGNI）。

### 4.3 右侧抽屉（`<body>` 末尾，与分享弹窗并列）

```html
<div class="kb-drawer-overlay" id="kbDrawerOverlay" style="display:none"></div>
<aside class="kb-drawer" id="kbDrawer" style="display:none">
    <div class="kb-drawer-header">
        <h3>📕 小红书知识库</h3>
        <button class="kb-drawer-close" id="kbDrawerClose">×</button>
    </div>
    <div class="kb-drawer-body">
        <section class="kb-section">
            <h4 class="kb-section-title">搜索并入库</h4>
            <div class="kb-form">
                <label class="kb-form-label">关键词 <span class="required">*</span></label>
                <input id="kbKeywordInput" class="kb-form-input" maxlength="50">
                <label class="kb-form-label">城市</label>
                <input id="kbCityInput" class="kb-form-input" maxlength="20">
                <label class="kb-form-label">抓取数量</label>
                <select id="kbCountSelect" class="kb-form-input">
                    <option value="3">3 条</option>
                    <option value="5" selected>5 条</option>
                    <option value="10">10 条</option>
                    <option value="20">20 条</option>
                </select>
                <button class="kb-ingest-btn" id="kbIngestBtn">
                    <span class="kb-ingest-btn-text">搜索并入库</span>
                    <span class="kb-ingest-btn-loading" style="display:none">
                        <span class="spinner-inline"></span> 入库中...
                    </span>
                </button>
                <div class="kb-ingest-status" id="kbIngestStatus"></div>
            </div>
        </section>
        <section class="kb-section">
            <h4 class="kb-section-title">
                我的知识库 <span class="kb-count" id="kbListCount">(0)</span>
                <button class="kb-refresh-btn" id="kbRefreshBtn" title="刷新">⟳</button>
            </h4>
            <div class="kb-list" id="kbList"></div>
            <div class="kb-empty" id="kbEmpty" style="display:none">
                还没有知识库，先用上面的表单搜索一个吧
            </div>
        </section>
    </div>
</aside>
```

### 4.4 单个 KB 卡片（JS 渲染，三态）

```html
<!-- 常态 -->
<div class="kb-item" data-kb="...">
    <div class="kb-item-main">
        <div class="kb-item-name">美食 | 成都</div>
        <div class="kb-item-meta">47 块 · 2026-05-14 15:30</div>
    </div>
    <button class="kb-item-delete" data-action="delete-prompt">🗑</button>
</div>

<!-- 选中态：左侧绿色竖条 + 高亮背景 -->
<div class="kb-item active" data-kb="...">
    <span class="kb-item-active-mark"></span>
    ...
</div>

<!-- 删除确认态 -->
<div class="kb-item confirming" data-kb="...">
    <div class="kb-item-main">
        <div class="kb-item-name">...</div>
        <div class="kb-item-meta">确认删除？此操作不可恢复</div>
    </div>
    <div class="kb-item-confirm-actions">
        <button class="kb-item-confirm-yes" data-action="delete-confirm">删除</button>
        <button class="kb-item-confirm-no" data-action="delete-cancel">取消</button>
    </div>
</div>
```

### 4.5 引用折叠条（assistant 消息内 markdown 之前）

```html
<details class="message-citations" data-count="3">
    <summary class="citations-summary">
        <span class="citations-icon">📕</span>
        <span class="citations-text">基于 3 条小红书攻略</span>
        <svg class="citations-chevron"><!-- 向下箭头 --></svg>
    </summary>
    <ul class="citations-list">
        <li>
            <span class="citation-idx">[1]</span>
            <a href="..." target="_blank" rel="noopener" class="citation-link">成都5日游</a>
            <span class="citation-meta">· 旅行达人 · 8832 赞</span>
        </li>
        ...
    </ul>
</details>
```

`<details>/<summary>` 是原生折叠元素，零 JS。

## 5. JS 行为（`static/app.js`）

### 5.1 全局状态（构造函数追加）

```js
this.currentMode = 'quick';   // 扩展枚举：+ 'rag'
this.kb = {
    selectedName: null,
    list: [], loaded: false, drawerOpen: false,
    pendingSendAfterSelect: false, pendingQuestion: '',
};
// 启动恢复
const savedKb = localStorage.getItem('xhs_selected_kb');
if (savedKb) this.kb.selectedName = savedKb;
```

### 5.2 KbMixin（行为聚合）

新增 mixin 对象，构造时 `Object.assign(this, KbMixin)`：

| 方法 | 说明 |
|---|---|
| `showKbBar() / hideKbBar()` | RAG 切换钩入 |
| `refreshKbBarLabel()` | 文案 = `description` 优先，否则 kb_name 末尾时间戳；tooltip 完整 kb_name |
| `openKbDrawer({refresh=true}) / closeKbDrawer()` | 抽屉显隐 + 首次自动 fetchKbList |
| `fetchKbList()` | `GET /api/xhs/kb/list`；校验 `selectedName` 仍存在，否则清空 |
| `ingestKb(keyword, city, count)` | `POST /api/xhs/ingest/mcp`；loading→success/empty/error；成功后**自动选中**新 KB |
| `deleteKb(kbName)` | `DELETE /api/xhs/kb/{kb}`；若删的是当前选中 → 清空 selectedName + localStorage |
| `selectKb(name, closeDrawer=true)` | 写 state + localStorage + 重渲染；触发 `pendingSendAfterSelect` 续发 |
| `renderKbList(override?, emptyMsg?)` | DOM 重建，active/confirming 态切换 |

### 5.3 事件绑定（构造函数 `init` 阶段追加）

- `#kbBarSelect` 点击 → `openKbDrawer({refresh:true})`
- `#kbBarManageBtn` 点击 → `openKbDrawer({refresh:true})`
- `#kbDrawerClose` / `#kbDrawerOverlay` 点击 → `closeKbDrawer()`
- `#kbIngestBtn` 点击 → 校验关键词非空 → `ingestKb(...)`
- `#kbRefreshBtn` 点击 → `fetchKbList()`
- `#kbList` 事件委托：
  - `[data-action=delete-prompt]` → 卡片切到 confirming 态
  - `[data-action=delete-confirm]` → `deleteKb()`
  - `[data-action=delete-cancel]` → `renderKbList()` 恢复
  - 点空白 → `selectKb(kbName)`

### 5.4 子模式切换（`setMode` 钩入）

```js
setMode(mode) {
    this.currentMode = mode;
    // ... 原有高亮 / 按钮文字
    if (mode === 'rag') {
        this.showKbBar();
        if (!this.kb.loaded) this.fetchKbList();  // 静默拉，不开抽屉
    } else {
        this.hideKbBar();
    }
    document.getElementById('currentModeText').textContent =
        { quick:'快速', stream:'流式', rag:'RAG' }[mode] || '快速';
}
```

### 5.5 `sendMessage` 增加 RAG 分支

```js
async sendMessage() {
    const question = this.messageInput.value.trim();
    if (!question) return;

    // RAG 前置：未选 KB → 缓存问题 + 弹抽屉
    if (this.currentMode === 'rag' && !this.kb.selectedName) {
        this.kb.pendingSendAfterSelect = true;
        this.kb.pendingQuestion = question;
        document.getElementById('kbBar').classList.add('warn');
        this.openKbDrawer({ refresh: true });
        return;
    }

    // 原有：渲染用户消息 + 清空输入框 ...

    if (this.currentMode === 'rag')      await this.sendRagStream(question);
    else if (this.currentMode === 'quick') await this.sendQuick(question);
    else                                  await this.sendStream(question);
}
```

### 5.6 `sendRagStream` SSE 处理

- `fetch('/api/chat/rag_stream', POST, JSON{Question, session_id, kb_name})`
- `reader.read()` 循环，按 `\n\n` 切事件，`data: ` 后是 JSON
- 事件类型：
  - `citations` → 调 `renderCitations(host, payload.data)` 注入消息上方
  - `content` → 累加 `fullText`，每次 `marked.parse(fullText)` 重渲染 + 滚到底
  - `done` → 收尾（无操作）
  - `error` → 红色错误气泡 + return
- 失败兜底：catch 块 → "网络错误：…"

### 5.7 `injectCitationsHost` / `renderCitations`

- `injectCitationsHost(assistantEl)`：在 `.markdown-content` 之前插一个空 `<details>`（`display:none`），返回它
- `renderCitations(hostEl, citations)`：citations 为空 → 保持 hidden；非空 → 显示 + 填充 `<summary>` + `<ul>`，URL 用 `escapeHtml` 转义

## 6. CSS（`static/styles.css`）

净增约 220 行，5 组：

1. `.kb-bar` 及内部按钮（淡橙黄 `#fef7e6` / `.warn` 红 + shake 动画）
2. `.kb-drawer` + overlay（420px、`translateX` 滑入 0.22s）
3. `.kb-form*` + `.kb-ingest-btn` + `.kb-ingest-status` 三态
4. `.kb-item` 三态（常态 / `.active` 绿 / `.confirming` 红）+ `.kb-empty`
5. `.message-citations` `<details>` 折叠（淡黄 `#fffbf0` 背景，向下箭头 `transform` 旋转）

色板严格沿用现有：`#202124` 文字 / `#5f6368` 次 / `#dadce0` 边框 / `#1a73e8` 主蓝 / `#34a853` 绿 / `#d93025` 红 / `#f9ab00` 黄。

不引入小红书品牌红 `#ff2442`——容易抢戏，emoji 📕 已足够表意。

响应式断点 `max-width: 520px`：抽屉全宽、KB bar 折行、citation-link 截断更窄。

## 7. 错误处理矩阵

| 场景 | UI 表现 |
|---|---|
| `/api/chat/rag_stream` 4xx/5xx | 红色助手气泡（如 404：知识库不存在） |
| SSE `type:error` 事件 | 同上 |
| `/api/xhs/kb/list` 失败 | 列表区"加载失败：<msg>"，表单仍可用 |
| `/api/xhs/ingest/mcp` 失败 | `.kb-ingest-status.err` 红字 |
| `/api/xhs/ingest/mcp` 0 笔记（data.kb_name=null） | `.kb-ingest-status.warn` "0 条笔记，未创建" |
| `DELETE /api/xhs/kb/...` 失败 | `alert()` 简提示（v1 不引入 toast） |
| SSE 网络断流 | 红色"网络错误：…" |
| localStorage KB 已被后端删除 | 拉 list 时清空 `selectedName`，KB bar 回"请选择" |
| 关键词为空点搜索 | `.kb-ingest-status.warn` "请填写关键词"，不发请求 |

## 8. 改动文件清单

| 文件 | 改动 | 净增行 |
|---|---|---|
| `static/index.html` | §4.1 / §4.2 / §4.3 | +60 |
| `static/styles.css` | §6 五组样式 | +220 |
| `static/app.js` | §5 KbMixin + sendRagStream + setMode 钩入 + sendMessage 分支 | +320 |

后端无任何改动（API 已就绪）。

## 9. 测试策略

### 9.1 不引入前端测试框架

YAGNI——纯 vanilla JS + CDN 项目，引入 Jest/Vitest 成本远大于本次改动收益。

### 9.2 浏览器手测矩阵（22 项）

| 编号 | 区域 | 场景 |
|---|---|---|
| T1 | 子模式切换 | quick ↔ stream ↔ rag 三向切换 |
| T2 | KB bar 显隐 | 仅 RAG 时显示，切回 quick/stream 隐藏 |
| T3 | KB bar 空态 | RAG + 未选 KB，点发送 → shake + 抽屉弹出 |
| T4 | 抽屉开关 | [管理] / × / overlay 三种关闭方式 |
| T5 | 入库 happy path | 表单 → loading → 成功 → 列表新增 → 自动选中 |
| T6 | 入库 0 笔记 | 用找不到的关键词 → "0 条笔记" |
| T7 | 入库失败 | 停 xhs MCP → 红字错误 |
| T8 | KB 列表渲染 | 计数/description/num_entities/created_at 正确 |
| T9 | 选中 KB | 点卡片 → 高亮 + 抽屉关 + KB bar 更新 |
| T10 | 删除二次确认 | 🗑 → 卡片变红 → 取消恢复 |
| T11 | 删除执行 | 确认 → DELETE → 列表刷新 |
| T12 | 删当前选中 KB | KB bar 回"请选择" |
| T13 | RAG 发送 happy path | 引用先到 + 内容流式 + 链接外跳 |
| T14 | RAG 命中 0 | citations 不显示，prompt 走 fallback |
| T15 | RAG KB 已删 | 红色 404 错误气泡 |
| T16 | RAG 服务 5xx | 红色"网络错误" |
| T17 | 子模式跨切的会话连续 | RAG 一轮 → quick 一轮能引用 |
| T18 | localStorage 持久 | 刷新后 KB 仍预选 |
| T19 | localStorage 失效 KB | 刷新后清空，无错 |
| T20 | 旅游模式不受影响 | KB bar 隐藏 |
| T21 | 普通 /chat 不受影响 | quick 子模式正常 |
| T22 | 窄屏 | DevTools ≤520px：抽屉全宽、bar 折行 |

### 9.3 SSE 协议验证

DevTools Network 面板看 `/api/chat/rag_stream`：
- 第一个事件**必须**是 `citations`（在所有 `content` 之前）
- 末尾 `done` 事件
- 全程无意外断开

### 9.4 Console sanity check

```js
console.table({
    currentMode:  window.__app.currentMode,
    selectedKb:   window.__app.kb.selectedName,
    drawerOpen:   window.__app.kb.drawerOpen,
    listLength:   window.__app.kb.list.length,
});
window.__app.fetchKbList().then(() => console.log(window.__app.kb.list));
```

### 9.5 不在测试范围

- 真实 XHS cookie 抓取链路
- KB > 50 时性能
- IE / 旧 Edge
- 移动端真机
- 后端测试（已 77 单元 + 4 集成覆盖）

## 10. 风险与权衡

- **localStorage 跨标签页不同步**：用户在 tab A 删除某 KB 后，tab B 的 `selectedName` 直到下次 `fetchKbList()` 才会被纠正。本期接受（用户多 tab 场景少）。
- **大量 KB 列表性能**：未做虚拟滚动；超过 ~50 个 KB 抽屉会很长。后续可加。
- **citations 与 content 顺序依赖**：依赖后端 SSE 严格先推 `citations` 再推 `content`。后端已实现且测试覆盖，前端按此假设处理。
- **没有 toast 组件**：删除失败等用 `alert()`，UI 略糙。本期接受，避免引入新组件。
- **`<details>` 在旧 Safari 默认折叠 polyfill** —— 项目目标浏览器是主流现代版本，不做兼容处理。
