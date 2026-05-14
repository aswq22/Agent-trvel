# 小红书 RAG 前端集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把后端已就绪的 `/api/chat/rag*` 与 `/api/xhs/*` 接入现有聊天 UI，作为第三个聊天子模式（快速/流式/**RAG**），并提供 KB 搜索入库/列表/切换/删除的可视化交互。

**Architecture:** 沿用现有 `class SuperBizAgentApp` 单一大类风格，往里加方法（不引入新 module/mixin）。在 `static/index.html` 加 DOM、`static/styles.css` 加样式、`static/app.js` 加约 320 行 JS。后端零改动。

**Tech Stack:** Vanilla JS（ES2020+ class）+ Fetch + ReadableStream（SSE）+ HTML `<details>/<summary>`（原生折叠）+ `localStorage`。继续用 CDN 的 marked / highlight.js。无新依赖。

**Spec:** `docs/superpowers/specs/2026-05-14-xhs-rag-frontend-design.md`

---

## 文件结构与改动范围

| 文件 | 改动 |
|---|---|
| `static/index.html` | +60 行：dropdown 加 RAG 项；`.chat-input-container` 内插入 `#kbBar`；body 末尾追加 `#kbDrawerOverlay` 和 `#kbDrawer` |
| `static/styles.css` | +220 行：`.kb-bar*` / `.kb-drawer*` / `.kb-form*` / `.kb-item*` / `.message-citations*` / 响应式 |
| `static/app.js` | +320 行：构造函数加 `this.kb` 状态、`initializeElements()` 缓存 DOM、`updateUI()` 钩入 RAG、`bindEvents()` 加 KB 事件、新增 9 个 KB 方法 + 重构 `sendMessage` 分支 + 新增 `sendRagStream` |

## 测试策略

按 spec §9.1：**不引入** Jest/Vitest。每个任务末尾以**浏览器手测**验证。Task 8 是完整 22 项验收清单。

---

## Task 1: HTML 骨架（DOM 三处插入）

**Files:**
- Modify: `static/index.html`

只做 HTML 改动。这一步完成后，浏览器里能看到 RAG 下拉项（点了无效果）和 KB bar（一直隐藏）。

- [ ] **Step 1.1: 在 `#modeDropdown` 内追加 RAG 项**

找到 `index.html` 中：

```html
<div class="dropdown-item" data-mode="stream">
    <div class="dropdown-item-main">
        <span>流式</span>
    </div>
    <div class="dropdown-item-sub">实时流式输出</div>
</div>
```

在它**之后**插入：

```html
<div class="dropdown-item" data-mode="rag">
    <div class="dropdown-item-main">
        <span>RAG · 小红书</span>
    </div>
    <div class="dropdown-item-sub">基于小红书攻略检索</div>
</div>
```

- [ ] **Step 1.2: 在 `.chat-input-container` 内、`.input-group-wrapper` 之前插入 KB bar**

找到：

```html
<div class="chat-input-container">
    <div class="input-group-wrapper">
```

把它替换成：

```html
<div class="chat-input-container">
    <div class="kb-bar" id="kbBar" style="display:none">
        <span class="kb-bar-icon">📕</span>
        <span class="kb-bar-label">知识库:</span>
        <button class="kb-bar-select" id="kbBarSelect" type="button">
            <span id="kbBarSelectedName" class="kb-bar-placeholder">请选择知识库</span>
            <svg class="dropdown-arrow" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M6 9L12 15L18 9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </button>
        <div class="kb-bar-spacer"></div>
        <button class="kb-bar-manage" id="kbBarManageBtn" type="button">
            <svg viewBox="0 0 24 24" fill="none" width="14" height="14" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 5V19M5 12H19" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <span>管理</span>
        </button>
    </div>
    <div class="input-group-wrapper">
```

- [ ] **Step 1.3: 在 body 末尾（在 `<script src="/static/app.js?v=3"></script>` 之前）插入抽屉**

```html
    <!-- 知识库抽屉 -->
    <div class="kb-drawer-overlay" id="kbDrawerOverlay" style="display:none"></div>
    <aside class="kb-drawer" id="kbDrawer" style="display:none">
        <div class="kb-drawer-header">
            <h3>📕 小红书知识库</h3>
            <button class="kb-drawer-close" id="kbDrawerClose" aria-label="关闭" type="button">×</button>
        </div>
        <div class="kb-drawer-body">
            <section class="kb-section">
                <h4 class="kb-section-title">搜索并入库</h4>
                <div class="kb-form">
                    <label class="kb-form-label">关键词 <span class="required">*</span></label>
                    <input type="text" id="kbKeywordInput" class="kb-form-input"
                           placeholder="如：美食、景点、攻略" maxlength="50">
                    <label class="kb-form-label">城市</label>
                    <input type="text" id="kbCityInput" class="kb-form-input"
                           placeholder="如：成都、北京（可空）" maxlength="20">
                    <label class="kb-form-label">抓取数量</label>
                    <select id="kbCountSelect" class="kb-form-input">
                        <option value="3">3 条</option>
                        <option value="5" selected>5 条</option>
                        <option value="10">10 条</option>
                        <option value="20">20 条</option>
                    </select>
                    <button class="kb-ingest-btn" id="kbIngestBtn" type="button">
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
                    <button class="kb-refresh-btn" id="kbRefreshBtn" title="刷新" type="button">⟳</button>
                </h4>
                <div class="kb-list" id="kbList"></div>
                <div class="kb-empty" id="kbEmpty" style="display:none">
                    还没有知识库，先用上面的表单搜索一个吧
                </div>
            </section>
        </div>
    </aside>
```

- [ ] **Step 1.4: 手测验证**

打开 http://localhost:9900（假设主服务已起，没起的话先 `python -m uvicorn app.main:app --port 9900`）。

- 点输入框右下角「快速 ▾」 → 下拉应出现 3 项：快速 / 流式 / **RAG · 小红书**
- 选 RAG 项**目前应无反应**（JS 还没钩进来）
- KB bar 完全看不见（因为 `display:none`）
- 浏览器 DevTools → Elements 里搜 `kbDrawer` 能找到（但 `display:none`）

- [ ] **Step 1.5: Commit**

```bash
git add static/index.html
git commit -m "feat(ui): scaffold XHS RAG DOM — dropdown item, KB bar, side drawer"
```

---

## Task 2: CSS（所有样式一次性加完）

**Files:**
- Modify: `static/styles.css`

加约 220 行样式到文件末尾。Task 1 已加的 DOM 此时会有外观（KB bar 仍隐藏因为 JS 没钩，但抽屉若手动改 `display:flex` 测试就能看到效果）。

- [ ] **Step 2.1: 把以下完整 CSS 块追加到 `static/styles.css` 末尾**

```css
/* ═══════════════════════════════════════════════════════════════════
   XHS RAG — KB Bar / Drawer / Citations
   ═══════════════════════════════════════════════════════════════════ */

/* ── KB Bar（输入框上方） ─────────────────────────────────────────── */
.kb-bar {
    display: none;
    align-items: center;
    gap: 10px;
    padding: 8px 14px;
    margin: 0 auto 8px;
    max-width: 760px;
    background: #fef7e6;
    border: 1px solid #fce7b8;
    border-radius: 10px;
    font-size: 13px;
    color: #202124;
}
.kb-bar.warn {
    background: #fce8e6;
    border-color: #f28b82;
    animation: kb-bar-shake .35s ease;
}
@keyframes kb-bar-shake {
    0%, 100% { transform: translateX(0); }
    25%      { transform: translateX(-4px); }
    75%      { transform: translateX(4px); }
}
.kb-bar-icon  { font-size: 14px; }
.kb-bar-label { color: #5f6368; }
.kb-bar-select {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 4px 10px; border-radius: 6px;
    background: #fff; border: 1px solid #dadce0;
    font-size: 13px; cursor: pointer;
    max-width: 260px;
    color: #202124;
    font-family: inherit;
}
.kb-bar-select:hover { background: #f8f9fa; }
.kb-bar-placeholder  { color: #80868b; }
.kb-bar-select #kbBarSelectedName {
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    max-width: 220px;
}
.kb-bar-select .dropdown-arrow { width: 14px; height: 14px; flex-shrink: 0; }
.kb-bar-spacer { flex: 1; }
.kb-bar-manage {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 4px 10px; border-radius: 6px;
    background: transparent; border: none; cursor: pointer;
    color: #1a73e8; font-size: 13px;
    font-family: inherit;
}
.kb-bar-manage:hover { background: rgba(26, 115, 232, 0.08); }

/* ── 右侧抽屉 ──────────────────────────────────────────────────── */
.kb-drawer-overlay {
    position: fixed; inset: 0; z-index: 50;
    background: rgba(0, 0, 0, 0.25);
}
.kb-drawer {
    position: fixed; top: 0; right: 0; bottom: 0;
    width: 420px; max-width: 100vw;
    background: #fff; z-index: 51;
    box-shadow: -4px 0 24px rgba(0, 0, 0, 0.12);
    display: flex; flex-direction: column;
    animation: kb-drawer-in .22s cubic-bezier(.4, 0, .2, 1);
}
@keyframes kb-drawer-in {
    from { transform: translateX(100%); }
    to   { transform: translateX(0); }
}
.kb-drawer-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid #dadce0;
    flex-shrink: 0;
}
.kb-drawer-header h3 {
    font-size: 16px; font-weight: 500; color: #202124; margin: 0;
}
.kb-drawer-close {
    border: none; background: none; cursor: pointer;
    width: 32px; height: 32px; border-radius: 50%;
    font-size: 20px; color: #5f6368;
    display: inline-flex; align-items: center; justify-content: center;
    line-height: 1;
}
.kb-drawer-close:hover { background: #f1f3f4; }
.kb-drawer-body {
    flex: 1; overflow-y: auto; padding: 20px;
}
.kb-section { margin-bottom: 28px; }
.kb-section-title {
    font-size: 13px; font-weight: 500; color: #5f6368;
    text-transform: uppercase; letter-spacing: 0.04em;
    margin: 0 0 12px 0;
    display: flex; align-items: center; gap: 8px;
}
.kb-count { color: #80868b; font-size: 12px; text-transform: none; }
.kb-refresh-btn {
    margin-left: auto; border: none; background: none; cursor: pointer;
    color: #5f6368; font-size: 14px; padding: 2px 6px; border-radius: 4px;
    font-family: inherit;
}
.kb-refresh-btn:hover { background: #f1f3f4; color: #202124; }

/* ── 搜索入库表单 ──────────────────────────────────────────────── */
.kb-form { display: flex; flex-direction: column; gap: 4px; }
.kb-form-label { font-size: 12px; color: #5f6368; margin-top: 8px; }
.kb-form-label .required { color: #d93025; }
.kb-form-input {
    padding: 10px 12px;
    border: 1px solid #dadce0; border-radius: 8px;
    font-size: 14px; font-family: inherit;
    background: #fff; color: #202124;
    outline: none; transition: border-color .15s;
}
.kb-form-input:focus { border-color: #1a73e8; }
.kb-ingest-btn {
    margin-top: 12px;
    padding: 10px 16px;
    background: #1a73e8; color: #fff;
    border: none; border-radius: 8px;
    font-size: 14px; font-weight: 500;
    cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    font-family: inherit;
}
.kb-ingest-btn:hover:not(:disabled) { background: #1666cc; }
.kb-ingest-btn:disabled             { background: #c6dafc; cursor: not-allowed; }
.kb-ingest-btn-loading { display: inline-flex; align-items: center; gap: 6px; }
.spinner-inline {
    width: 14px; height: 14px;
    border: 2px solid rgba(255, 255, 255, 0.4);
    border-top-color: #fff;
    border-radius: 50%;
    animation: kb-spin .8s linear infinite;
}
@keyframes kb-spin { to { transform: rotate(360deg); } }
.kb-ingest-status      { font-size: 12px; margin-top: 8px; min-height: 16px; }
.kb-ingest-status.ok   { color: #1e8e3e; }
.kb-ingest-status.warn { color: #f9ab00; }
.kb-ingest-status.err  { color: #d93025; }

/* ── KB 列表 ──────────────────────────────────────────────────── */
.kb-list { display: flex; flex-direction: column; gap: 8px; }
.kb-item {
    position: relative;
    display: flex; align-items: center; gap: 10px;
    padding: 12px;
    border: 1px solid #dadce0; border-radius: 10px;
    background: #fff; cursor: pointer;
    transition: background .15s, border-color .15s;
}
.kb-item:hover           { background: #f8f9fa; border-color: #c0c4ca; }
.kb-item.active          { background: #e6f4ea; border-color: #34a853; }
.kb-item.confirming      { background: #fce8e6; border-color: #f28b82; cursor: default; }
.kb-item-active-mark {
    position: absolute; left: -1px; top: 8px; bottom: 8px;
    width: 3px; background: #34a853; border-radius: 2px;
}
.kb-item-main { flex: 1; min-width: 0; }
.kb-item-name {
    font-size: 14px; color: #202124; font-weight: 500;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.kb-item-meta { font-size: 12px; color: #5f6368; margin-top: 2px; }
.kb-item.confirming .kb-item-meta { color: #d93025; }
.kb-item-delete {
    border: none; background: none; cursor: pointer;
    width: 30px; height: 30px; border-radius: 50%;
    font-size: 14px; color: #5f6368;
    display: inline-flex; align-items: center; justify-content: center;
}
.kb-item-delete:hover { background: #f1f3f4; color: #d93025; }
.kb-item-confirm-actions { display: flex; gap: 6px; }
.kb-item-confirm-yes,
.kb-item-confirm-no {
    border: none; border-radius: 6px; padding: 6px 12px;
    font-size: 12px; cursor: pointer; font-family: inherit;
}
.kb-item-confirm-yes        { background: #d93025; color: #fff; }
.kb-item-confirm-yes:hover  { background: #b71c1c; }
.kb-item-confirm-no         { background: #fff; color: #5f6368; border: 1px solid #dadce0; }
.kb-item-confirm-no:hover   { background: #f1f3f4; }
.kb-empty {
    text-align: center; color: #80868b; font-size: 13px;
    padding: 24px 12px;
}

/* ── 消息内引用折叠条 ──────────────────────────────────────────── */
.message-citations {
    margin-bottom: 10px;
    border: 1px solid #fce7b8;
    border-radius: 8px;
    background: #fffbf0;
    font-size: 13px;
    overflow: hidden;
}
.message-citations[open] { background: #fefcf6; }
.citations-summary {
    list-style: none;
    display: flex; align-items: center; gap: 8px;
    padding: 8px 12px;
    cursor: pointer; user-select: none;
}
.citations-summary::-webkit-details-marker { display: none; }
.citations-icon { font-size: 14px; }
.citations-text { flex: 1; color: #5f6368; }
.citations-chevron {
    width: 16px; height: 16px; color: #5f6368;
    transition: transform .2s;
    flex-shrink: 0;
}
.message-citations[open] .citations-chevron { transform: rotate(180deg); }
.citations-list {
    list-style: none;
    padding: 4px 12px 10px 12px;
    margin: 0;
    border-top: 1px dashed #fce7b8;
}
.citations-list li {
    padding: 4px 0;
    display: flex; align-items: baseline; gap: 4px;
    flex-wrap: wrap;
}
.citation-idx { color: #80868b; font-variant-numeric: tabular-nums; }
.citation-link {
    color: #1a73e8; text-decoration: none;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    max-width: 320px;
}
.citation-link:hover { text-decoration: underline; }
.citation-meta       { color: #5f6368; font-size: 12px; }

/* ── 窄屏响应式 ──────────────────────────────────────────────── */
@media (max-width: 520px) {
    .kb-drawer { width: 100vw; }
    .kb-bar {
        padding: 6px 10px;
        font-size: 12px;
        flex-wrap: wrap;
    }
    .kb-bar-spacer  { display: none; }
    .citation-link  { max-width: 200px; }
}
```

- [ ] **Step 2.2: 手测验证**

刷新页面（Ctrl-F5 强刷以避免 CSS 缓存）。

在 DevTools Console 跑：

```js
document.getElementById('kbBar').style.display = 'flex';
document.getElementById('kbDrawerOverlay').style.display = 'block';
document.getElementById('kbDrawer').style.display = 'flex';
```

应该看到：
- 输入框上方出现淡橙色 KB bar
- 右侧滑出 420px 抽屉（带半透明遮罩），含搜索表单 + 空的 KB 列表
- 抽屉 × 按钮可见

再跑：

```js
document.getElementById('kbBar').style.display = 'none';
document.getElementById('kbDrawerOverlay').style.display = 'none';
document.getElementById('kbDrawer').style.display = 'none';
```

恢复隐藏。

- [ ] **Step 2.3: Commit**

```bash
git add static/styles.css
git commit -m "feat(ui): add CSS for KB bar, side drawer, ingest form, list, citations"
```

---

## Task 3: JS 状态 + DOM 缓存 + RAG 子模式钩入

**Files:**
- Modify: `static/app.js`

把 RAG 子模式接入现有的 `selectChatSubMode` / `updateUI` / `bindEvents`。本任务后切到 RAG 子模式时 KB bar 出现，但点 [管理] 还没反应。

- [ ] **Step 3.1: 在 constructor 末尾加 `this.kb` 状态**

找到 `static/app.js` 的：

```js
this.initializeElements();
this.bindEvents();
this.updateUI();
```

在它**之前**插入：

```js
// XHS RAG 状态
this.kb = {
    selectedName: null,
    list: [],
    loaded: false,
    drawerOpen: false,
    pendingSendAfterSelect: false,
    pendingQuestion: '',
};
const savedKb = localStorage.getItem('xhs_selected_kb');
if (savedKb) this.kb.selectedName = savedKb;
```

- [ ] **Step 3.2: 在 `initializeElements()` 末尾追加 KB DOM 引用**

找到 `initializeElements()` 方法的末尾（`this.chatHistoryList = document.getElementById('chatHistoryList');` 那一行之后），追加：

```js
// XHS RAG DOM
this.kbBar              = document.getElementById('kbBar');
this.kbBarSelect        = document.getElementById('kbBarSelect');
this.kbBarSelectedName  = document.getElementById('kbBarSelectedName');
this.kbBarManageBtn     = document.getElementById('kbBarManageBtn');
this.kbDrawer           = document.getElementById('kbDrawer');
this.kbDrawerOverlay    = document.getElementById('kbDrawerOverlay');
this.kbDrawerClose      = document.getElementById('kbDrawerClose');
this.kbKeywordInput     = document.getElementById('kbKeywordInput');
this.kbCityInput        = document.getElementById('kbCityInput');
this.kbCountSelect      = document.getElementById('kbCountSelect');
this.kbIngestBtn        = document.getElementById('kbIngestBtn');
this.kbIngestStatus     = document.getElementById('kbIngestStatus');
this.kbList             = document.getElementById('kbList');
this.kbListCount        = document.getElementById('kbListCount');
this.kbEmpty            = document.getElementById('kbEmpty');
this.kbRefreshBtn       = document.getElementById('kbRefreshBtn');
```

- [ ] **Step 3.3: 在 `selectChatSubMode` 改文案以支持 RAG**

找到现有：

```js
selectChatSubMode(mode) {
    if (this.isStreaming) { this.showNotification('请等待当前对话完成后再切换', 'warning'); return; }
    this.currentMode = mode;
    this.updateUI();
    this.showNotification(`已切换到${mode === 'quick' ? '快速' : '流式'}模式`, 'info');
}
```

替换为：

```js
selectChatSubMode(mode) {
    if (this.isStreaming) { this.showNotification('请等待当前对话完成后再切换', 'warning'); return; }
    this.currentMode = mode;
    this.updateUI();
    const label = { quick: '快速', stream: '流式', rag: 'RAG · 小红书' }[mode] || mode;
    this.showNotification(`已切换到${label}模式`, 'info');
    // RAG 首次切入时静默拉一次列表
    if (mode === 'rag' && !this.kb.loaded) {
        this.fetchKbList();
    }
}
```

- [ ] **Step 3.4: 在 `updateUI()` 钩入 RAG 显隐**

找到 `updateUI()` 内的这一段：

```js
// 聊天子模式文字
if (this.currentModeText && !isTravel) {
    this.currentModeText.textContent = this.currentMode === 'quick' ? '快速' : '流式';
}
```

替换为：

```js
// 聊天子模式文字
if (this.currentModeText && !isTravel) {
    this.currentModeText.textContent =
        { quick: '快速', stream: '流式', rag: 'RAG' }[this.currentMode] || '快速';
}

// XHS RAG：KB bar 显隐
if (this.kbBar) {
    const showKbBar = !isTravel && this.currentMode === 'rag';
    this.kbBar.style.display = showKbBar ? 'flex' : 'none';
    if (showKbBar) this.refreshKbBarLabel();
}
```

- [ ] **Step 3.5: 在 `static/app.js` 的 `class SuperBizAgentApp` **类末尾** （即最后一个方法之后、闭合 `}` 之前）追加 `refreshKbBarLabel` 占位方法**

```js
// ─── XHS RAG ────────────────────────────────────────────────────────────

refreshKbBarLabel() {
    if (!this.kbBarSelectedName) return;
    if (!this.kb.selectedName) {
        this.kbBarSelectedName.textContent = '请选择知识库';
        this.kbBarSelectedName.classList.add('kb-bar-placeholder');
        this.kbBarSelectedName.title = '';
    } else {
        const item = this.kb.list.find(x => x.kb_name === this.kb.selectedName);
        const fallback = this.kb.selectedName.split('_').pop();
        this.kbBarSelectedName.textContent = (item && item.description) || fallback;
        this.kbBarSelectedName.classList.remove('kb-bar-placeholder');
        this.kbBarSelectedName.title = this.kb.selectedName;
    }
    // 用户操作意图改变后清掉警告动画
    if (this.kbBar) this.kbBar.classList.remove('warn');
}

// fetchKbList 占位 —— Task 4 实现
async fetchKbList() { /* implemented in Task 4 */ }
```

- [ ] **Step 3.6: 手测验证**

刷新页面。
- 切到「RAG · 小红书」子模式 → KB bar 出现，显示"请选择知识库"
- 切回「快速」或「流式」→ KB bar 消失
- 切到「旅游规划」app mode → KB bar 也消失

DevTools Console 跑：

```js
console.log(window.__app.kb);
```

应输出 `{selectedName: null, list: [], loaded: false, drawerOpen: false, pendingSendAfterSelect: false, pendingQuestion: ''}`

- [ ] **Step 3.7: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): wire RAG sub-mode toggle and KB bar visibility"
```

---

## Task 4: JS — fetchKbList / renderKbList / selectKb（核心数据流）

**Files:**
- Modify: `static/app.js`

实现「拉列表 → 渲染卡片 → 点击选中」。本任务后通过 console 调用 `fetchKbList()` 就能在 DOM 里看到列表。

- [ ] **Step 4.1: 在前面 Task 3.5 加的 `// fetchKbList 占位` 那行下面，**替换占位实现**为：**

```js
async fetchKbList() {
    if (!this.kbList) return;
    try {
        const resp = await fetch(`${this.apiBaseUrl}/xhs/kb/list`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const body = await resp.json();
        if (body.code !== 200) throw new Error(body.message || '加载失败');
        this.kb.list = body.data.kbs || [];
        this.kb.loaded = true;
        // 失效校验：localStorage 中的 selectedName 不存在则清空
        if (this.kb.selectedName && !this.kb.list.find(x => x.kb_name === this.kb.selectedName)) {
            this.kb.selectedName = null;
            localStorage.removeItem('xhs_selected_kb');
        }
        this.renderKbList();
        this.refreshKbBarLabel();
    } catch (e) {
        this.renderKbList([], `加载失败：${e.message}`);
    }
}

renderKbList(overrideList = null, emptyMsg = '') {
    const list = overrideList || this.kb.list;
    if (this.kbListCount) this.kbListCount.textContent = `(${list.length})`;
    if (!this.kbList) return;
    this.kbList.innerHTML = '';
    if (!list.length) {
        if (this.kbEmpty) {
            this.kbEmpty.style.display = '';
            this.kbEmpty.textContent = emptyMsg || '还没有知识库，先用上面的表单搜索一个吧';
        }
        return;
    }
    if (this.kbEmpty) this.kbEmpty.style.display = 'none';
    for (const kb of list) {
        const div = document.createElement('div');
        const isActive = kb.kb_name === this.kb.selectedName;
        div.className = 'kb-item' + (isActive ? ' active' : '');
        div.dataset.kb = kb.kb_name;
        const displayName = kb.description || kb.kb_name;
        const meta = `${kb.num_entities} 块 · ${kb.created_at || '—'}`;
        div.innerHTML = `
            ${isActive ? '<span class="kb-item-active-mark"></span>' : ''}
            <div class="kb-item-main">
                <div class="kb-item-name" title="${this.escapeHtml(kb.kb_name)}">${this.escapeHtml(displayName)}</div>
                <div class="kb-item-meta">${this.escapeHtml(meta)}</div>
            </div>
            <button class="kb-item-delete" data-action="delete-prompt" title="删除" type="button">🗑</button>
        `;
        this.kbList.appendChild(div);
    }
}

selectKb(name, closeDrawer = true) {
    this.kb.selectedName = name;
    if (name) localStorage.setItem('xhs_selected_kb', name);
    else      localStorage.removeItem('xhs_selected_kb');
    this.renderKbList();
    this.refreshKbBarLabel();
    if (closeDrawer) this.closeKbDrawer();
    // 触发被无 KB 拦截的待发问题
    if (this.kb.pendingSendAfterSelect && this.kb.pendingQuestion) {
        const q = this.kb.pendingQuestion;
        this.kb.pendingSendAfterSelect = false;
        this.kb.pendingQuestion = '';
        if (this.messageInput) this.messageInput.value = q;
        this.sendMessage();
    }
}

// closeKbDrawer 占位 —— Task 5 实现
closeKbDrawer() { /* implemented in Task 5 */ }
```

- [ ] **Step 4.2: 手测验证**

前置：用 curl 入库一条数据（如果还没有）：

```powershell
curl.exe -X POST http://localhost:9900/api/xhs/ingest/mcp `
  -H "Content-Type: application/json" `
  -d '{\"keyword\":\"美食\",\"city\":\"成都\",\"count\":5}'
```

浏览器刷新 → 切到 RAG 模式（这会触发 Step 3.3 里的自动 fetchKbList）→ DevTools Console：

```js
console.log(window.__app.kb.list);
```

应能看到一个 kbs 数组。手动开抽屉验证渲染：

```js
document.getElementById('kbDrawer').style.display = 'flex';
document.getElementById('kbDrawerOverlay').style.display = 'block';
window.__app.renderKbList();
```

应看到 KB 列表有 1 张卡片，显示"美食|成都"、"X 块 · 2026-05-14 ..."。

测试 selectKb：

```js
window.__app.selectKb('xhs_xxx_...');  // 用实际的 kb_name
```

→ 抽屉里那张卡片左侧出现绿条 + 背景变绿；KB bar 文案变成"美食|成都"。

关闭：

```js
document.getElementById('kbDrawer').style.display = 'none';
document.getElementById('kbDrawerOverlay').style.display = 'none';
```

- [ ] **Step 4.3: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): fetchKbList/renderKbList/selectKb with localStorage validation"
```

---

## Task 5: JS — 抽屉开关 + 事件绑定

**Files:**
- Modify: `static/app.js`

把 KB bar 按钮和抽屉关闭按钮绑定起来。本任务后点 [管理] / 点 KB 文字、点关闭都能用。

- [ ] **Step 5.1: 把 Task 4.1 末尾的 `closeKbDrawer() { /* implemented in Task 5 */ }` 替换为完整实现**

```js
async openKbDrawer({ refresh = true } = {}) {
    if (!this.kbDrawer) return;
    this.kbDrawer.style.display          = 'flex';
    this.kbDrawerOverlay.style.display   = 'block';
    this.kb.drawerOpen = true;
    if (refresh || !this.kb.loaded) {
        await this.fetchKbList();
    }
}

closeKbDrawer() {
    if (!this.kbDrawer) return;
    this.kbDrawer.style.display        = 'none';
    this.kbDrawerOverlay.style.display = 'none';
    this.kb.drawerOpen = false;
}
```

- [ ] **Step 5.2: 在 `bindEvents()` 方法末尾追加 KB 事件绑定**

找到 `bindEvents()` 的最后一行 `if (this.fileInput) this.fileInput.addEventListener('change', e => this.handleFileSelect(e));`，在它之后追加：

```js
// ── XHS RAG events ──────────────────────────────────────────
if (this.kbBarSelect) {
    this.kbBarSelect.addEventListener('click', () => this.openKbDrawer({ refresh: true }));
}
if (this.kbBarManageBtn) {
    this.kbBarManageBtn.addEventListener('click', () => this.openKbDrawer({ refresh: true }));
}
if (this.kbDrawerClose) {
    this.kbDrawerClose.addEventListener('click', () => this.closeKbDrawer());
}
if (this.kbDrawerOverlay) {
    this.kbDrawerOverlay.addEventListener('click', () => this.closeKbDrawer());
}
if (this.kbRefreshBtn) {
    this.kbRefreshBtn.addEventListener('click', () => this.fetchKbList());
}
// KB 列表点击委托（select / delete-prompt / delete-confirm / delete-cancel）
if (this.kbList) {
    this.kbList.addEventListener('click', (e) => this.onKbListClick(e));
}
// 入库按钮
if (this.kbIngestBtn) {
    this.kbIngestBtn.addEventListener('click', () => this.onIngestClick());
}
```

- [ ] **Step 5.3: 在类末尾追加 `onKbListClick` 与 `onIngestClick` 占位**

```js
onKbListClick(e) {
    const itemEl = e.target.closest('.kb-item');
    if (!itemEl) return;
    const kbName = itemEl.dataset.kb;
    const action = e.target.closest('[data-action]')?.dataset.action;

    if (action === 'delete-prompt' || action === 'delete-confirm' || action === 'delete-cancel') {
        // implemented in Task 6
        return;
    }
    // 默认：点空白 = 选中
    this.selectKb(kbName);
}

onIngestClick() {
    // implemented in Task 7
}
```

- [ ] **Step 5.4: 手测验证**

刷新 → 切到 RAG 模式：
- 点 KB bar 上的「请选择知识库 ▾」 → 抽屉滑出，列表有数据
- 点抽屉 × → 关闭
- 重开 → 点 overlay（抽屉外灰色区域）→ 关闭
- 重开 → 点列表里某个 KB 卡片（非 🗑）→ 抽屉关闭、KB bar 显示该 KB 名字、卡片有绿色高亮（再次开抽屉验证）
- 点 KB bar 上的「管理」按钮 → 抽屉同样打开
- 点抽屉里 ⟳ 刷新 → 列表重新加载（无可视差异，但 Network 面板能看到一次 GET）

- [ ] **Step 5.5: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): wire KB drawer open/close and list-click event delegation"
```

---

## Task 6: JS — 删除 + 二次确认

**Files:**
- Modify: `static/app.js`

把 Task 5.3 占位的删除逻辑完整实现。本任务后能用抽屉里的 🗑 删 KB。

- [ ] **Step 6.1: 替换 `onKbListClick` 的删除分支**

把 Task 5.3 加的 `onKbListClick` 整个方法**替换**为：

```js
onKbListClick(e) {
    const itemEl = e.target.closest('.kb-item');
    if (!itemEl) return;
    const kbName = itemEl.dataset.kb;
    const action = e.target.closest('[data-action]')?.dataset.action;

    if (action === 'delete-prompt') {
        e.stopPropagation();
        this.enterDeleteConfirmMode(itemEl);
        return;
    }
    if (action === 'delete-confirm') {
        e.stopPropagation();
        this.deleteKb(kbName);
        return;
    }
    if (action === 'delete-cancel') {
        e.stopPropagation();
        this.renderKbList();   // 整列重渲染 = 退出确认态最简单
        return;
    }
    // 默认：点空白 = 选中
    this.selectKb(kbName);
}
```

- [ ] **Step 6.2: 在类末尾追加 `enterDeleteConfirmMode` 和 `deleteKb`**

```js
enterDeleteConfirmMode(itemEl) {
    // 切到 confirming 态：替换 .kb-item-delete 按钮为两个确认按钮
    itemEl.classList.add('confirming');
    const meta = itemEl.querySelector('.kb-item-meta');
    if (meta) meta.textContent = '确认删除？此操作不可恢复';
    const deleteBtn = itemEl.querySelector('.kb-item-delete');
    if (!deleteBtn) return;
    const actions = document.createElement('div');
    actions.className = 'kb-item-confirm-actions';
    actions.innerHTML = `
        <button class="kb-item-confirm-yes" data-action="delete-confirm" type="button">删除</button>
        <button class="kb-item-confirm-no"  data-action="delete-cancel"  type="button">取消</button>
    `;
    deleteBtn.replaceWith(actions);
}

async deleteKb(kbName) {
    try {
        const resp = await fetch(`${this.apiBaseUrl}/xhs/kb/${encodeURIComponent(kbName)}`, {
            method: 'DELETE',
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const body = await resp.json();
        if (body.code !== 200) throw new Error(body.message || '删除失败');
        // 若删的是当前选中的 KB，清空选择
        if (this.kb.selectedName === kbName) {
            this.kb.selectedName = null;
            localStorage.removeItem('xhs_selected_kb');
        }
        await this.fetchKbList();
        this.showNotification('知识库已删除', 'success');
    } catch (e) {
        this.showNotification(`删除失败：${e.message}`, 'error');
    }
}
```

- [ ] **Step 6.3: 手测验证**

前置：有至少 2 个 KB（不够就用 curl 再入一条不同 keyword 的）。

切到 RAG → 开抽屉 → 点某行 🗑：
- 该行变红、文案换成"确认删除？此操作不可恢复"，🗑 替换为 [删除] / [取消]
- 点 [取消] → 行恢复常态
- 再次 🗑 → 点 [删除] → 行消失，列表计数 -1，右上角弹出"知识库已删除"
- 若删的是当前选中的 KB → KB bar 回到"请选择知识库"

- [ ] **Step 6.4: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): KB deletion with inline two-step confirm"
```

---

## Task 7: JS — 搜索入库

**Files:**
- Modify: `static/app.js`

把 `/api/xhs/ingest/mcp` 接进抽屉的入库表单。

- [ ] **Step 7.1: 把 Task 5.3 加的 `onIngestClick()` 替换为完整实现，并在类末尾追加 `ingestKb` 方法**

替换 `onIngestClick()` 为：

```js
onIngestClick() {
    const keyword = this.kbKeywordInput ? this.kbKeywordInput.value.trim() : '';
    const city    = this.kbCityInput    ? this.kbCityInput.value.trim()    : '';
    const count   = this.kbCountSelect  ? parseInt(this.kbCountSelect.value, 10) : 5;
    if (!keyword) {
        this.setIngestStatus('请填写关键词', 'warn');
        return;
    }
    this.ingestKb(keyword, city, count);
}
```

在类末尾追加：

```js
setIngestStatus(text, level) {
    if (!this.kbIngestStatus) return;
    this.kbIngestStatus.textContent = text;
    this.kbIngestStatus.className = 'kb-ingest-status' + (level ? ' ' + level : '');
}

setIngestLoading(loading) {
    if (!this.kbIngestBtn) return;
    this.kbIngestBtn.disabled = loading;
    const txt   = this.kbIngestBtn.querySelector('.kb-ingest-btn-text');
    const ldg   = this.kbIngestBtn.querySelector('.kb-ingest-btn-loading');
    if (txt) txt.style.display = loading ? 'none' : '';
    if (ldg) ldg.style.display = loading ? 'inline-flex' : 'none';
}

async ingestKb(keyword, city, count) {
    this.setIngestLoading(true);
    this.setIngestStatus('', '');
    try {
        const resp = await fetch(`${this.apiBaseUrl}/xhs/ingest/mcp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keyword, city, count }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const body = await resp.json();
        if (body.code !== 200) throw new Error(body.message || '入库失败');
        const data = body.data || {};
        if (!data.kb_name) {
            this.setIngestStatus('0 条笔记，未创建知识库', 'warn');
            return;
        }
        this.setIngestStatus(`✓ 已入库 ${data.ingested} 笔记 / ${data.chunks} 块`, 'ok');
        await this.fetchKbList();
        // 自动选中新建的 KB，但不关闭抽屉（让用户看到自己刚建的列表项）
        this.selectKb(data.kb_name, false);
    } catch (e) {
        this.setIngestStatus(`✗ ${e.message}`, 'err');
    } finally {
        this.setIngestLoading(false);
    }
}
```

- [ ] **Step 7.2: 手测验证**

切 RAG → 开抽屉：
- 关键词空 → 点搜索 → 状态行黄字"请填写关键词"
- 填关键词"景点"、城市"杭州"、数量 5 → 点搜索 → 按钮变 spinner + "入库中..." → 数秒后变绿字"✓ 已入库 X 笔记 / Y 块"，列表多了一条 KB，且该 KB 自动高亮（绿条），抽屉**不**自动关
- 临时停掉 xhs MCP 进程（窗口 Ctrl-C），再点搜索 → 红字错误消息（MCP 连接失败...）

- [ ] **Step 7.3: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): XHS MCP ingest from drawer with progress + status messages"
```

---

## Task 8: JS — sendMessage RAG 分支 + sendRagStream + citations

**Files:**
- Modify: `static/app.js`

最大一块：把 RAG 子模式的发送链路打通，处理 SSE 三种事件 + 引用渲染。

- [ ] **Step 8.1: 修改 `sendMessage` 的 dispatch 逻辑**

找到现有 `sendMessage()` 的这部分：

```js
this.addMessage('user', message);
if (this.messageInput) this.messageInput.value = '';
this.isStreaming = true;
this.updateUI();

try {
    if (this.appMode === 'travel') {
        await this.sendTravelRequest(message);
    } else if (this.currentMode === 'quick') {
        await this.sendQuickMessage(message);
    } else {
        await this.sendStreamMessage(message);
    }
}
```

**整体替换**为（注意 RAG 前置校验要在 addMessage 之前）：

```js
// RAG 前置：未选 KB → 缓存问题、shake KB bar、弹抽屉
if (this.appMode !== 'travel' && this.currentMode === 'rag' && !this.kb.selectedName) {
    this.kb.pendingSendAfterSelect = true;
    this.kb.pendingQuestion = message;
    if (this.kbBar) this.kbBar.classList.add('warn');
    this.openKbDrawer({ refresh: true });
    return;
}

this.addMessage('user', message);
if (this.messageInput) this.messageInput.value = '';
this.isStreaming = true;
this.updateUI();

try {
    if (this.appMode === 'travel') {
        await this.sendTravelRequest(message);
    } else if (this.currentMode === 'rag') {
        await this.sendRagStream(message);
    } else if (this.currentMode === 'quick') {
        await this.sendQuickMessage(message);
    } else {
        await this.sendStreamMessage(message);
    }
}
```

- [ ] **Step 8.2: 在类末尾追加 `sendRagStream` 和 `renderCitations` 两个方法**

```js
async sendRagStream(message) {
    const msgEl = this.addMessage('assistant', '', true);  // 流式 stub
    let citationsEl = null;
    let fullResponse = '';

    const resp = await fetch(`${this.apiBaseUrl}/chat/rag_stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            Question:   message,
            session_id: this.sessionId,
            kb_name:    this.kb.selectedName,
        }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) { this.handleStreamComplete(msgEl, fullResponse); break; }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
                if (!line.startsWith('data:')) continue;
                const raw = line.slice(5).trim();
                if (!raw) continue;
                let payload;
                try { payload = JSON.parse(raw); } catch (_) { continue; }

                if (payload.type === 'citations') {
                    citationsEl = this.renderCitations(msgEl, payload.data || []);
                } else if (payload.type === 'content') {
                    fullResponse += payload.data || '';
                    const mc = msgEl.querySelector('.message-content');
                    if (mc) {
                        mc.innerHTML = this.renderMarkdown(fullResponse);
                        this.highlightCodeBlocks(mc);
                    }
                    this.scrollToBottom();
                } else if (payload.type === 'done') {
                    this.handleStreamComplete(msgEl, fullResponse);
                    return;
                } else if (payload.type === 'error') {
                    const mc = msgEl.querySelector('.message-content');
                    if (mc) mc.innerHTML = this.renderMarkdown('错误: ' + (payload.data || '未知错误'));
                    return;
                }
            }
        }
    } finally {
        reader.releaseLock();
    }
}

renderCitations(msgEl, citations) {
    if (!msgEl || !citations || citations.length === 0) return null;
    const wrapper = msgEl.querySelector('.message-content-wrapper');
    if (!wrapper) return null;
    // 避免重复插入（首个 citations 事件之后通常不会再来）
    let det = wrapper.querySelector('.message-citations');
    if (!det) {
        det = document.createElement('details');
        det.className = 'message-citations';
        // 插到 .message-content 之前
        const mc = wrapper.querySelector('.message-content');
        wrapper.insertBefore(det, mc);
    }
    det.dataset.count = citations.length;
    const itemsHtml = citations.map((c, i) => {
        const title  = this.escapeHtml(c.title || '(无标题)');
        const url    = this.escapeHtml(c.url || '#');
        const author = this.escapeHtml(c.author || '匿名');
        const likes  = Number(c.likes) || 0;
        return `
            <li>
                <span class="citation-idx">[${i + 1}]</span>
                <a href="${url}" target="_blank" rel="noopener" class="citation-link">${title}</a>
                <span class="citation-meta">· ${author} · ${likes} 赞</span>
            </li>
        `;
    }).join('');
    det.innerHTML = `
        <summary class="citations-summary">
            <span class="citations-icon">📕</span>
            <span class="citations-text">基于 ${citations.length} 条小红书攻略</span>
            <svg class="citations-chevron" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M6 9L12 15L18 9" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
        </summary>
        <ul class="citations-list">${itemsHtml}</ul>
    `;
    return det;
}
```

- [ ] **Step 8.3: 手测验证（happy path）**

前置：至少有一个含数据的 KB（用 Task 7 入库的"成都美食"那条）。

切 RAG → 选定 KB → 输入"成都有什么必吃美食"→ 发送：

1. 用户消息气泡出现
2. 助手气泡出现，**先**出现"📕 基于 3 条小红书攻略"折叠条
3. **然后**正文开始流式逐字打字
4. 流完后点折叠条 → 展开看到 `[1] xxx · 作者 · X 赞`，链接可点跳转新标签

DevTools Network 面板检查 `/chat/rag_stream`：第一个事件 `citations`、若干 `content`、末尾 `done`。

- [ ] **Step 8.4: 手测验证（边界场景）**

| 场景 | 操作 | 期望 |
|---|---|---|
| 未选 KB 点发送 | RAG + KB bar 显示"请选择" → 输入 + 点发送 | KB bar shake 红边 + 抽屉自动弹出 + 未发送消息；在抽屉里选一个 KB → 自动补发该消息 |
| 0 命中 | 选成都美食 KB，问"火箭怎么造" | citations 折叠条**不**出现；正文带"以下为通用建议"开头 |
| KB 已删 | 选 KB 后在抽屉里手动删它，再发送 | 红色错误气泡"知识库 'xxx' 不存在" 或 HTTP 404 |
| 服务挂 | 关闭 uvicorn 主服务 → 发送 | 红色错误（fetch 错误或网络错误） |

- [ ] **Step 8.5: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): wire /chat/rag_stream SSE with citations preceding content"
```

---

## Task 9: 端到端验收 + 完整手测矩阵

**Files:** 无新改动；按 spec §9.2 的 22 项清单回归。

- [ ] **Step 9.1: 准备数据**

启动并预热（如果还没起）：

```powershell
# 终端 1
docker compose -f vector-database.yml up -d

# 终端 2
.venv\Scripts\activate
python mcp_servers/xhs_server.py

# 终端 3
.venv\Scripts\activate
python -m uvicorn app.main:app --port 9900

# 终端 4：入两个有内容的 KB
curl.exe -X POST http://localhost:9900/api/xhs/ingest/mcp `
  -H "Content-Type: application/json" `
  -d '{\"keyword\":\"美食\",\"city\":\"成都\",\"count\":5}'
curl.exe -X POST http://localhost:9900/api/xhs/ingest/mcp `
  -H "Content-Type: application/json" `
  -d '{\"keyword\":\"景点\",\"city\":\"北京\",\"count\":5}'
```

打开 http://localhost:9900 + F12 DevTools。

- [ ] **Step 9.2: 跑 22 项清单（spec §9.2）**

逐项打勾验证；每条 ≤ 30 秒。

| # | 场景 | 通过标志 |
|---|---|---|
| T1 | quick ↔ stream ↔ rag 三向切换 | 三个子模式间无残留状态，KB bar 跟随 |
| T2 | KB bar 显隐 | 仅 RAG 时显示 |
| T3 | RAG + 未选 KB，点发送 | shake + 抽屉自动开 |
| T4 | 抽屉关 × / overlay 都能用 | 都能正常关 |
| T5 | 入库 happy path | 表单提交 → spinner → 绿字 → 列表新增 + 自动选中 |
| T6 | 入库 0 笔记 | 用很冷僻的关键词如"火星攻略"（Mock 找不到）→ 黄字 "0 条" |
| T7 | 入库失败 | 停掉 xhs_server.py → 入库 → 红字错误 |
| T8 | KB 列表渲染 | 计数 / description / num_entities / created_at 都对 |
| T9 | 选中 KB | 卡片高亮 + 抽屉关 + KB bar 文案 |
| T10 | 删除二次确认 | 🗑 → 红框 + 两按钮；取消 → 恢复 |
| T11 | 删除执行 | 确认 → DELETE → 列表 -1 |
| T12 | 删当前选中 KB | KB bar 回"请选择" |
| T13 | RAG 发送 happy path | citations 先到 + 流式 + 链接可跳 |
| T14 | RAG 命中 0 | citations **不**显示 |
| T15 | RAG KB 已删 | 红色 404 |
| T16 | RAG 服务 5xx | 关 uvicorn → 红色"网络错误" |
| T17 | 跨子模式会话连续 | RAG 答一轮 → 切 quick 追问"那门票呢" → 能基于上下文回答 |
| T18 | localStorage 持久 | 选 KB → F5 刷新 → KB bar 仍预选；切到 RAG 直接能发 |
| T19 | localStorage 失效 KB | 选 KB → 用 curl DELETE 该 KB → F5 刷新 → KB bar 回"请选择"，无错 |
| T20 | 旅游模式不受影响 | 切到旅游规划 tab → KB bar 隐藏 |
| T21 | 普通 /chat 不受影响 | 切 quick → 正常聊天，无 RAG 痕迹 |
| T22 | 窄屏 | DevTools 调到 480px → 抽屉全宽、KB bar 折行不溢出 |

- [ ] **Step 9.3: Console sanity check**

```js
console.table({
    currentMode:  window.__app.currentMode,
    appMode:      window.__app.appMode,
    selectedKb:   window.__app.kb.selectedName,
    drawerOpen:   window.__app.kb.drawerOpen,
    listLength:   window.__app.kb.list.length,
    pendingSend:  window.__app.kb.pendingSendAfterSelect,
});

// 主动调一次拉列表
window.__app.fetchKbList().then(() => console.log(window.__app.kb.list));
```

应正常打印，无红色 error。

- [ ] **Step 9.4: 验收门槛**

- T1–T22 全部通过
- DevTools Console 全程无红色 error（除已知 marked / hljs 弃用警告）
- Network 面板里 `/chat/rag_stream` 第一个事件**必须**是 `citations`，最后一个是 `done`
- 回归确认 T20 + T21：旅游规划、quick/stream 聊天毫无影响

- [ ] **Step 9.5: 若有任何项失败 → 修 + 回到对应 Task 重测；全过则提示完工**

完工后不再单独 commit（前面 8 个 task 的 commit 已覆盖代码）。可选：写一条 changelog entry 到 README，但**只在用户要求时做**。
