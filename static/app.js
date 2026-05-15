// 智能旅游助手 — 双模式前端
class SuperBizAgentApp {
    constructor() {
        this.travelUI = new TravelUI(this);
        this.apiBaseUrl = '/api';
        this.appMode = 'chat';       // 'chat' | 'travel'
        this.currentMode = 'quick';  // chat 子模式：'quick' | 'stream'
        this.sessionId = this.generateSessionId();
        this.isStreaming = false;
        this.currentChatHistory = [];
        this.chatHistories = this.loadChatHistories();
        this.isCurrentChatFromHistory = false;

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

        this.initializeElements();
        this.bindEvents();
        this.updateUI();
        this.initMarkdown();
        this.checkAndSetCentered();
        this.renderChatHistory();
    }

    // ─── Markdown ────────────────────────────────────────────────────────────

    initMarkdown() {
        const check = () => {
            if (typeof marked !== 'undefined') {
                try {
                    marked.setOptions({ breaks: true, gfm: true, headerIds: false, mangle: false });
                    if (typeof hljs !== 'undefined') {
                        marked.setOptions({
                            highlight: (code, lang) => {
                                if (lang && hljs.getLanguage(lang)) {
                                    try { return hljs.highlight(code, { language: lang }).value; } catch (_) {}
                                }
                                return code;
                            }
                        });
                    }
                } catch (e) { console.error('Markdown 配置失败:', e); }
            } else {
                setTimeout(check, 100);
            }
        };
        check();
    }

    renderMarkdown(content) {
        if (!content) return '';
        if (typeof marked === 'undefined') return this.escapeHtml(content);
        try { return marked.parse(content); } catch (_) { return this.escapeHtml(content); }
    }

    highlightCodeBlocks(container) {
        if (typeof hljs !== 'undefined' && container) {
            container.querySelectorAll('pre code').forEach(block => {
                if (!block.classList.contains('hljs')) hljs.highlightElement(block);
            });
        }
    }

    // ─── DOM ─────────────────────────────────────────────────────────────────

    initializeElements() {
        this.sidebar = document.querySelector('.sidebar');
        this.newChatBtn = document.getElementById('newChatBtn');
        this.chatModeTab = document.getElementById('chatModeTab');
        this.travelModeTab = document.getElementById('travelModeTab');
        this.currentModeBadge = document.getElementById('currentModeBadge');
        this.currentModeBadgeText = document.getElementById('currentModeBadgeText');
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.toolsBtn = document.getElementById('toolsBtn');
        this.toolsMenu = document.getElementById('toolsMenu');
        this.uploadFileItem = document.getElementById('uploadFileItem');
        this.chatSubModeWrapper = document.getElementById('chatSubModeWrapper');
        this.modeSelectorBtn = document.getElementById('modeSelectorBtn');
        this.modeDropdown = document.getElementById('modeDropdown');
        this.currentModeText = document.getElementById('currentModeText');
        this.fileInput = document.getElementById('fileInput');
        this.chatMessages = document.getElementById('chatMessages');
        this.loadingOverlay = document.getElementById('loadingOverlay');
        this.chatContainer = document.querySelector('.chat-container');
        this.welcomeGreeting = document.getElementById('welcomeGreeting');
        this.welcomeText = document.getElementById('welcomeText');
        this.welcomeSub = document.getElementById('welcomeSub');
        this.chatHistoryList = document.getElementById('chatHistoryList');
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
    }

    // ─── Events ──────────────────────────────────────────────────────────────

    bindEvents() {
        if (this.newChatBtn) this.newChatBtn.addEventListener('click', () => this.newChat());

        // 应用模式切换标签
        [this.chatModeTab, this.travelModeTab].forEach(tab => {
            if (tab) tab.addEventListener('click', () => this.switchAppMode(tab.dataset.appMode));
        });

        // 聊天子模式下拉
        if (this.modeSelectorBtn) {
            this.modeSelectorBtn.addEventListener('click', e => {
                e.stopPropagation();
                this.toggleModeDropdown();
            });
        }
        document.querySelectorAll('.dropdown-item').forEach(item => {
            item.addEventListener('click', () => {
                this.selectChatSubMode(item.getAttribute('data-mode'));
                this.closeModeDropdown();
            });
        });
        document.addEventListener('click', e => {
            if (this.modeSelectorBtn && !this.modeSelectorBtn.contains(e.target) &&
                this.modeDropdown && !this.modeDropdown.contains(e.target)) {
                this.closeModeDropdown();
            }
        });

        // 发送
        if (this.sendButton) this.sendButton.addEventListener('click', () => this.sendMessage());
        if (this.messageInput) {
            this.messageInput.addEventListener('keypress', e => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.sendMessage(); }
            });
        }

        // 工具菜单
        if (this.toolsBtn) {
            this.toolsBtn.addEventListener('click', e => { e.stopPropagation(); this.toggleToolsMenu(); });
        }
        if (this.uploadFileItem) {
            this.uploadFileItem.addEventListener('click', () => {
                if (this.fileInput) this.fileInput.click();
                this.closeToolsMenu();
            });
        }
        document.addEventListener('click', e => {
            if (this.toolsBtn && this.toolsMenu &&
                !this.toolsBtn.contains(e.target) && !this.toolsMenu.contains(e.target)) {
                this.closeToolsMenu();
            }
        });
        if (this.fileInput) this.fileInput.addEventListener('change', e => this.handleFileSelect(e));
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
    }

    // ─── App Mode Switching ──────────────────────────────────────────────────

    switchAppMode(mode) {
        if (this.isStreaming) {
            this.showNotification('请等待当前操作完成后再切换模式', 'warning');
            return;
        }
        this.appMode = mode;
        document.querySelectorAll('.app-mode-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.appMode === mode);
        });

        const travelLayout = document.getElementById('travelLayout');
        const chatContainer = document.querySelector('.chat-container');
        const modeBadge = document.getElementById('currentModeBadge');

        if (mode === 'travel') {
            if (chatContainer) chatContainer.style.display = 'none';
            if (travelLayout) travelLayout.classList.add('visible');
            if (modeBadge) modeBadge.style.display = 'none';
        } else {
            if (chatContainer) chatContainer.style.display = '';
            if (travelLayout) travelLayout.classList.remove('visible');
            if (modeBadge) modeBadge.style.display = '';
            this.updateUI();
        }

        const label = mode === 'travel' ? '旅游规划模式' : '聊天模式';
        this.showNotification(`已切换到${label}`, 'info');
    }

    // ─── Chat Sub-mode ───────────────────────────────────────────────────────

    toggleModeDropdown() {
        const wrapper = this.modeSelectorBtn && this.modeSelectorBtn.closest('.mode-selector-wrapper');
        if (wrapper) wrapper.classList.toggle('active');
    }

    closeModeDropdown() {
        const wrapper = this.modeSelectorBtn && this.modeSelectorBtn.closest('.mode-selector-wrapper');
        if (wrapper) wrapper.classList.remove('active');
    }

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

    // ─── UI Update ───────────────────────────────────────────────────────────

    updateUI() {
        const isTravel = this.appMode === 'travel';

        // 当前模式徽标
        if (this.currentModeBadgeText) {
            this.currentModeBadgeText.textContent = isTravel ? '旅游规划模式' : '聊天模式';
        }
        if (this.currentModeBadge) {
            this.currentModeBadge.className = `current-mode-badge ${isTravel ? 'travel' : 'chat'}`;
        }

        // 欢迎语
        if (this.welcomeText) {
            this.welcomeText.textContent = isTravel
                ? '规划您的专属旅程'
                : '你好！我是智能旅游助手';
        }
        if (this.welcomeSub) {
            this.welcomeSub.textContent = isTravel
                ? '输入旅行需求，多 Agent 协作为您生成完整攻略'
                : '可以跟我聊天，也可以切换到「旅游规划」制作专属攻略';
        }

        // 输入框 placeholder
        if (this.messageInput) {
            this.messageInput.placeholder = isTravel
                ? '描述旅行需求，例如：帮我规划5天成都之旅，预算5000元...'
                : '问问智能旅游助手...';
            this.messageInput.disabled = this.isStreaming;
        }

        // 聊天子模式选择器：旅游规划模式下隐藏
        if (this.chatSubModeWrapper) {
            this.chatSubModeWrapper.style.display = isTravel ? 'none' : '';
        }

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

        // 下拉激活状态
        document.querySelectorAll('.dropdown-item').forEach(item => {
            item.classList.toggle('active', item.getAttribute('data-mode') === this.currentMode);
        });

        // 发送按钮
        if (this.sendButton) this.sendButton.disabled = this.isStreaming;
    }

    // ─── New Chat / History ──────────────────────────────────────────────────

    newChat() {
        if (this.isStreaming) { this.showNotification('请等待当前对话完成后再新建对话', 'warning'); return; }
        if (this.currentChatHistory.length > 0) {
            if (this.isCurrentChatFromHistory) this.updateCurrentChatHistory();
            else this.saveCurrentChat();
        }
        this.isStreaming = false;
        if (this.messageInput) this.messageInput.value = '';
        this.currentChatHistory = [];
        this.isCurrentChatFromHistory = false;
        if (this.chatMessages) this.chatMessages.innerHTML = '';
        this.sessionId = this.generateSessionId();
        this.currentMode = 'quick';
        this.updateUI();
        this.checkAndSetCentered();
        this.renderChatHistory();
    }

    saveCurrentChat() {
        if (!this.currentChatHistory.length) return;
        const exists = this.chatHistories.findIndex(h => h.id === this.sessionId);
        if (exists !== -1) { this.updateCurrentChatHistory(); return; }
        const firstUser = this.currentChatHistory.find(m => m.type === 'user');
        const title = firstUser
            ? firstUser.content.substring(0, 30) + (firstUser.content.length > 30 ? '...' : '')
            : '新对话';
        this.chatHistories.unshift({
            id: this.sessionId, title,
            messages: [...this.currentChatHistory],
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
        });
        if (this.chatHistories.length > 50) this.chatHistories = this.chatHistories.slice(0, 50);
        this.saveChatHistories();
    }

    updateCurrentChatHistory() {
        if (!this.currentChatHistory.length) return;
        const idx = this.chatHistories.findIndex(h => h.id === this.sessionId);
        if (idx === -1) { this.saveCurrentChat(); return; }
        const h = this.chatHistories[idx];
        h.messages = [...this.currentChatHistory];
        h.updatedAt = new Date().toISOString();
        const firstUser = this.currentChatHistory.find(m => m.type === 'user');
        if (firstUser) h.title = firstUser.content.substring(0, 30) + (firstUser.content.length > 30 ? '...' : '');
        this.saveChatHistories();
    }

    loadChatHistories() {
        try { return JSON.parse(localStorage.getItem('chatHistories') || '[]'); }
        catch (_) { return []; }
    }

    saveChatHistories() {
        try { localStorage.setItem('chatHistories', JSON.stringify(this.chatHistories)); }
        catch (_) {}
    }

    renderChatHistory() {
        if (!this.chatHistoryList) return;
        this.chatHistoryList.innerHTML = '';
        this.chatHistories.forEach(history => {
            const item = document.createElement('div');
            item.className = 'history-item';
            item.dataset.historyId = history.id;
            item.innerHTML = `
                <div class="history-item-content">
                    <span class="history-item-title">${this.escapeHtml(history.title)}</span>
                </div>
                <button class="history-item-delete" data-history-id="${history.id}" title="删除">
                    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                </button>`;
            item.addEventListener('click', e => {
                if (!e.target.closest('.history-item-delete')) this.loadChatHistory(history.id);
            });
            item.querySelector('.history-item-delete').addEventListener('click', e => {
                e.stopPropagation();
                this.deleteChatHistory(history.id);
            });
            this.chatHistoryList.appendChild(item);
        });
    }

    async loadChatHistory(historyId) {
        const history = this.chatHistories.find(h => h.id === historyId);
        if (!history) return;
        if (this.currentChatHistory.length > 0 && this.sessionId !== historyId) {
            if (this.isCurrentChatFromHistory) this.updateCurrentChatHistory();
            else this.saveCurrentChat();
        }
        try {
            const resp = await fetch(`${this.apiBaseUrl}/chat/session/${historyId}`);
            if (resp.ok) {
                const data = await resp.json();
                const backendHistory = data.history || [];
                this.sessionId = history.id;
                this.isCurrentChatFromHistory = true;
                if (this.chatMessages) {
                    this.chatMessages.innerHTML = '';
                    if (backendHistory.length > 0) {
                        this.currentChatHistory = [];
                        backendHistory.forEach(m => this.addMessage(m.role === 'user' ? 'user' : 'assistant', m.content, false, false));
                    } else {
                        this.currentChatHistory = [...history.messages];
                        history.messages.forEach(m => this.addMessage(m.type, m.content, false, false));
                    }
                }
            } else {
                this.sessionId = history.id;
                this.currentChatHistory = [...history.messages];
                this.isCurrentChatFromHistory = true;
                if (this.chatMessages) {
                    this.chatMessages.innerHTML = '';
                    history.messages.forEach(m => this.addMessage(m.type, m.content, false, false));
                }
            }
        } catch (_) {
            this.sessionId = history.id;
            this.currentChatHistory = [...history.messages];
            this.isCurrentChatFromHistory = true;
            if (this.chatMessages) {
                this.chatMessages.innerHTML = '';
                history.messages.forEach(m => this.addMessage(m.type, m.content, false, false));
            }
        }
        this.checkAndSetCentered();
        this.renderChatHistory();
    }

    async deleteChatHistory(historyId) {
        try {
            const resp = await fetch(`${this.apiBaseUrl}/chat/clear`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: historyId }),
            });
            const result = await resp.json();
            if (result.status === 'success') {
                this.chatHistories = this.chatHistories.filter(h => h.id !== historyId);
                this.saveChatHistories();
                this.renderChatHistory();
                if (this.sessionId === historyId) {
                    this.currentChatHistory = [];
                    if (this.chatMessages) this.chatMessages.innerHTML = '';
                    this.sessionId = this.generateSessionId();
                    this.checkAndSetCentered();
                }
                this.showNotification('会话已清空', 'success');
            } else {
                throw new Error(result.message || '清空失败');
            }
        } catch (e) {
            this.showNotification('删除失败: ' + e.message, 'error');
        }
    }

    // ─── Send Message (dispatcher) ───────────────────────────────────────────

    async sendMessage() {
        const message = this.messageInput ? this.messageInput.value.trim() : '';
        if (!message) { this.showNotification('请输入内容', 'warning'); return; }
        if (this.isStreaming) { this.showNotification('请等待当前对话完成', 'warning'); return; }

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
        } catch (e) {
            console.error('发送失败:', e);
            this.addMessage('assistant', '抱歉，请求出现错误：' + e.message);
        } finally {
            this.isStreaming = false;
            this.updateUI();
            if (this.isCurrentChatFromHistory && this.currentChatHistory.length > 0) {
                this.updateCurrentChatHistory();
                this.renderChatHistory();
            }
        }
    }

    // ─── Chat: Quick ─────────────────────────────────────────────────────────

    async sendQuickMessage(message) {
        const loadingMsg = this.addLoadingMessage('正在思考...');
        try {
            const resp = await fetch(`${this.apiBaseUrl}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ Id: this.sessionId, Question: message }),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            if (loadingMsg && loadingMsg.parentNode) loadingMsg.parentNode.removeChild(loadingMsg);
            if (data.code === 200 || data.message === 'success') {
                const chatResp = data.data;
                if (chatResp && chatResp.success) {
                    this.addMessage('assistant', chatResp.answer || '（无回复内容）');
                } else if (chatResp && chatResp.errorMessage) {
                    throw new Error(chatResp.errorMessage);
                } else {
                    this.addMessage('assistant', chatResp?.answer || '服务返回了空内容');
                }
            } else {
                throw new Error(data.message || '请求失败');
            }
        } catch (e) {
            if (loadingMsg && loadingMsg.parentNode) loadingMsg.parentNode.removeChild(loadingMsg);
            throw e;
        }
    }

    // ─── Chat: Stream ─────────────────────────────────────────────────────────

    async sendStreamMessage(message) {
        const resp = await fetch(`${this.apiBaseUrl}/chat_stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ Id: this.sessionId, Question: message }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

        const msgEl = this.addMessage('assistant', '', true);
        let fullResponse = '';
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
                    if (raw === '[DONE]') { this.handleStreamComplete(msgEl, fullResponse); return; }
                    try {
                        const msg = JSON.parse(raw);
                        if (msg.type === 'content') {
                            fullResponse += msg.data || '';
                            const mc = msgEl.querySelector('.message-content');
                            if (mc) { mc.innerHTML = this.renderMarkdown(fullResponse); this.highlightCodeBlocks(mc); }
                            this.scrollToBottom();
                        } else if (msg.type === 'done') {
                            this.handleStreamComplete(msgEl, fullResponse);
                            return;
                        } else if (msg.type === 'error') {
                            const mc = msgEl.querySelector('.message-content');
                            if (mc) mc.innerHTML = this.renderMarkdown('错误: ' + (msg.data || '未知错误'));
                            return;
                        }
                    } catch (_) {
                        fullResponse += raw;
                        const mc = msgEl.querySelector('.message-content');
                        if (mc) { mc.innerHTML = this.renderMarkdown(fullResponse); this.scrollToBottom(); }
                    }
                }
            }
        } finally {
            reader.releaseLock();
        }
    }

    // ─── Travel: SSE Planning ────────────────────────────────────────────────

    async sendTravelRequest(userInput) {
        const progressEl = this.addTravelProgressMessage();
        try {
            const resp = await fetch(`${this.apiBaseUrl}/travel/plan`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_input: userInput, session_id: this.sessionId }),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            try {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) {
                        this.showTravelError(progressEl, '规划流程异常结束，请重试');
                        break;
                    }
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';
                    for (const line of lines) {
                        if (!line.startsWith('data:')) continue;
                        const raw = line.slice(5).trim();
                        if (!raw) continue;
                        try {
                            const event = JSON.parse(raw);
                            if (event.type === 'progress') {
                                this.updateTravelProgress(progressEl, event.stage, event.message);
                            } else if (event.type === 'complete') {
                                this.showTravelPlan(progressEl, event.final_plan);
                                return;
                            } else if (event.type === 'error') {
                                this.showTravelError(progressEl, event.message);
                                return;
                            }
                        } catch (_) {}
                    }
                }
            } finally {
                reader.releaseLock();
            }
        } catch (e) {
            this.showTravelError(progressEl, e.message);
            // Don't rethrow — error is displayed in progress bubble
        }
    }

    // 旅游规划进度气泡
    addTravelProgressMessage() {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message assistant';

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" fill="white"/>
        </svg>`;
        msgDiv.appendChild(avatar);

        const wrapper = document.createElement('div');
        wrapper.className = 'message-content-wrapper';
        const content = document.createElement('div');
        content.className = 'message-content travel-progress-content';
        content.innerHTML = `
            <div class="travel-progress-header">
                <span class="ts-spinner"></span>
                <span>旅游规划中，请稍候...</span>
            </div>
            <div class="travel-stages-list">
                <div class="ts-item ts-pending"><span class="ts-icon">○</span>&nbsp;解析旅行参数</div>
                <div class="ts-item ts-pending"><span class="ts-icon">○</span>&nbsp;搜索景点推荐</div>
                <div class="ts-item ts-pending"><span class="ts-icon">○</span>&nbsp;规划路线 · 搜索酒店 · 推荐美食</div>
                <div class="ts-item ts-pending"><span class="ts-icon">○</span>&nbsp;生成完整攻略</div>
            </div>`;
        wrapper.appendChild(content);
        msgDiv.appendChild(wrapper);

        if (this.chatMessages) {
            this.chatMessages.appendChild(msgDiv);
            if (this.chatContainer) this.chatContainer.classList.remove('centered');
            this.scrollToBottom();
        }
        return msgDiv;
    }

    // stage 进度更新
    updateTravelProgress(msgEl, stage, message) {
        const STAGE_IDX = { parsing: 0, attractions: 1, route: 2, hotels: 2, food: 2, strategy: 3 };
        const LABELS = [
            '解析旅行参数',
            '搜索景点推荐',
            '规划路线 · 搜索酒店 · 推荐美食',
            '生成完整攻略',
        ];
        const activeIdx = STAGE_IDX[stage];
        if (activeIdx === undefined) return;

        const items = msgEl.querySelectorAll('.ts-item');
        items.forEach((el, i) => {
            if (i < activeIdx) {
                el.className = 'ts-item ts-done';
                el.innerHTML = `<span class="ts-icon ts-check">✓</span>&nbsp;${LABELS[i]}`;
            } else if (i === activeIdx) {
                el.className = 'ts-item ts-active';
                el.innerHTML = `<span class="ts-spinner-sm"></span>&nbsp;${message || LABELS[i]}`;
            } else {
                el.className = 'ts-item ts-pending';
                el.innerHTML = `<span class="ts-icon">○</span>&nbsp;${LABELS[i]}`;
            }
        });
        this.scrollToBottom();
    }

    // 展示最终攻略
    showTravelPlan(msgEl, plan) {
        const wrapper = msgEl.querySelector('.message-content-wrapper');
        if (!wrapper) return;

        // 用新的 message-content 替换 progress 内容
        const content = msgEl.querySelector('.message-content');
        if (content) {
            content.className = 'message-content';
            content.innerHTML = this.renderMarkdown(plan);
            this.highlightCodeBlocks(content);
        }

        this.currentChatHistory.push({ type: 'assistant', content: plan, timestamp: new Date().toISOString() });
        this.scrollToBottom();
    }

    // 展示规划出错
    showTravelError(msgEl, message) {
        const content = msgEl.querySelector('.message-content');
        if (content) {
            content.className = 'message-content';
            content.textContent = '规划出错：' + message;
        }
        this.scrollToBottom();
    }

    // ─── Message Rendering ───────────────────────────────────────────────────

    addMessage(type, content, isStreaming = false, saveToHistory = true) {
        const isFirstMessage = this.chatMessages && this.chatMessages.querySelectorAll('.message').length === 0;
        if (!isStreaming && saveToHistory && content) {
            this.currentChatHistory.push({ type, content, timestamp: new Date().toISOString() });
        }

        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${type}${isStreaming ? ' streaming' : ''}`;

        if (type === 'assistant') {
            const avatar = document.createElement('div');
            avatar.className = 'message-avatar';
            avatar.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" fill="white"/>
            </svg>`;
            msgDiv.appendChild(avatar);
        }

        const cw = document.createElement('div');
        cw.className = 'message-content-wrapper';
        const mc = document.createElement('div');
        mc.className = 'message-content';
        if (type === 'assistant' && !isStreaming) {
            mc.innerHTML = this.renderMarkdown(content);
            this.highlightCodeBlocks(mc);
        } else {
            mc.textContent = content;
        }
        cw.appendChild(mc);
        msgDiv.appendChild(cw);

        if (this.chatMessages) {
            this.chatMessages.appendChild(msgDiv);
            if (isFirstMessage && this.chatContainer) {
                this.chatContainer.classList.remove('centered');
                this.chatContainer.style.transition = 'all 0.5s ease';
            }
            this.scrollToBottom();
        }
        return msgDiv;
    }

    addLoadingMessage(content) {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message assistant';
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" fill="white"/>
        </svg>`;
        msgDiv.appendChild(avatar);

        const cw = document.createElement('div');
        cw.className = 'message-content-wrapper';
        const mc = document.createElement('div');
        mc.className = 'message-content loading-message-content';
        const textSpan = document.createElement('span');
        textSpan.textContent = content;
        const icon = document.createElement('span');
        icon.className = 'loading-spinner-icon';
        icon.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" fill="currentColor" opacity="0.2"/>
            <path d="M12 2C6.48 2 2 6.48 2 12c0 1.54.36 3 1 4.28L15 3c-1-.64-1.84-1-3-1z" fill="currentColor"/>
        </svg>`;
        mc.appendChild(textSpan);
        mc.appendChild(icon);
        cw.appendChild(mc);
        msgDiv.appendChild(cw);

        if (this.chatMessages) {
            this.chatMessages.appendChild(msgDiv);
            const isFirst = this.chatMessages.querySelectorAll('.message').length === 1;
            if (isFirst && this.chatContainer) this.chatContainer.classList.remove('centered');
            this.scrollToBottom();
        }
        return msgDiv;
    }

    handleStreamComplete(msgEl, fullResponse) {
        if (msgEl) {
            msgEl.classList.remove('streaming');
            const mc = msgEl.querySelector('.message-content');
            if (mc) { mc.innerHTML = this.renderMarkdown(fullResponse); this.highlightCodeBlocks(mc); }
        }
        if (fullResponse) {
            this.currentChatHistory.push({ type: 'assistant', content: fullResponse, timestamp: new Date().toISOString() });
            if (this.isCurrentChatFromHistory) { this.updateCurrentChatHistory(); this.renderChatHistory(); }
        }
    }

    checkAndSetCentered() {
        if (this.chatMessages && this.chatContainer) {
            const has = this.chatMessages.querySelectorAll('.message').length > 0;
            this.chatContainer.classList.toggle('centered', !has);
        }
    }

    scrollToBottom() {
        if (this.chatMessages) this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    // ─── File Upload ─────────────────────────────────────────────────────────

    toggleToolsMenu() {
        const wrapper = this.toolsBtn && this.toolsBtn.closest('.tools-btn-wrapper');
        if (wrapper) wrapper.classList.toggle('active');
    }

    closeToolsMenu() {
        const wrapper = this.toolsBtn && this.toolsBtn.closest('.tools-btn-wrapper');
        if (wrapper) wrapper.classList.remove('active');
    }

    handleFileSelect(e) {
        const file = e.target.files[0];
        if (!file) return;
        if (!this.validateFileType(file)) {
            this.showNotification('只支持 TXT 或 Markdown (.md) 格式', 'error');
            this.fileInput.value = '';
            return;
        }
        this.uploadFile(file);
    }

    validateFileType(file) {
        return ['.txt', '.md', '.markdown'].some(ext => file.name.toLowerCase().endsWith(ext));
    }

    async uploadFile(file) {
        if (file.size > 50 * 1024 * 1024) { this.showNotification('文件大小不能超过50MB', 'error'); return; }
        this.isStreaming = true;
        this.updateUI();
        if (this.loadingOverlay) {
            this.loadingOverlay.style.display = 'flex';
            const lt = this.loadingOverlay.querySelector('.loading-text');
            const ls = this.loadingOverlay.querySelector('.loading-subtext');
            if (lt) lt.textContent = '正在上传文件...';
            if (ls) ls.textContent = file.name;
            document.body.style.overflow = 'hidden';
        }
        try {
            const fd = new FormData();
            fd.append('file', file);
            const resp = await fetch(`${this.apiBaseUrl}/upload`, { method: 'POST', body: fd });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            if ((data.code === 200 || data.message === 'success') && data.data) {
                this.addMessage('assistant', `${file.name} 上传成功`, false, true);
            } else {
                throw new Error(data.message || '上传失败');
            }
        } catch (e) {
            this.showNotification('文件上传失败: ' + e.message, 'error');
        } finally {
            if (this.fileInput) this.fileInput.value = '';
            this.isStreaming = false;
            if (this.loadingOverlay) { this.loadingOverlay.style.display = 'none'; document.body.style.overflow = ''; }
            this.updateUI();
        }
    }

    // ─── Utilities ───────────────────────────────────────────────────────────

    generateSessionId() {
        return 'session_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
    }

    escapeHtml(text) {
        const d = document.createElement('div');
        d.textContent = text;
        return d.innerHTML;
    }

    showNotification(message, type = 'info') {
        const n = document.createElement('div');
        n.className = `notification ${type}`;
        n.textContent = message;
        n.style.cssText = `position:fixed;top:20px;right:20px;padding:12px 18px;border-radius:8px;color:white;font-weight:500;z-index:10000;animation:slideIn 0.3s ease;max-width:320px;`;
        const colors = { info: '#1a73e8', success: '#34a853', warning: '#fbbc04', error: '#ea4335' };
        n.style.backgroundColor = colors[type] || colors.info;
        document.body.appendChild(n);
        setTimeout(() => {
            n.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => { if (n.parentNode) n.parentNode.removeChild(n); }, 300);
        }, 3000);
    }

    // ─── XHS RAG ────────────────────────────────────────────────────────────

    refreshKbBarLabel() {
        if (!this.kbBarSelectedName) return;
        if (!this.kb.selectedName) {
            this.kbBarSelectedName.textContent = '🌐 全部知识库';
            this.kbBarSelectedName.title = '未选择具体知识库时，跨所有 xhs 分区检索';
        } else {
            const item = this.kb.list.find(x => x.kb_name === this.kb.selectedName);
            const label = (item && item.description) || '(未命名)';
            this.kbBarSelectedName.textContent = label;
            this.kbBarSelectedName.title = this.kb.selectedName;
        }
        if (this.kbBar) this.kbBar.classList.remove('warn');
    }

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

        // 列表顶部固定一项「🌐 全部知识库」，data-kb="" → selectKb(null) 走全局
        const allItem = document.createElement('div');
        const allActive = !this.kb.selectedName;
        allItem.className = 'kb-item kb-item-all' + (allActive ? ' active' : '');
        allItem.dataset.kb = '';
        allItem.innerHTML = `
            ${allActive ? '<span class="kb-item-active-mark"></span>' : ''}
            <div class="kb-item-main">
                <div class="kb-item-name">🌐 全部知识库</div>
                <div class="kb-item-meta">跨所有 xhs 分区检索（默认）</div>
            </div>
        `;
        this.kbList.appendChild(allItem);

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
            const displayName = kb.description || '(未命名)';
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

    onKbListClick(e) {
        const itemEl = e.target.closest('.kb-item');
        if (!itemEl) return;
        // 空 data-kb = "全部知识库" 项 → selectKb(null) 切回全局
        const kbName = itemEl.dataset.kb || null;
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
}

// 动画
const _style = document.createElement('style');
_style.textContent = `
@keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
@keyframes slideOut { from { transform: translateX(0); opacity: 1; } to { transform: translateX(100%); opacity: 0; } }
`;
document.head.appendChild(_style);

// ═══════════════════════════════════════════════════════════
// TravelUI — 旅游规划工作台
// ═══════════════════════════════════════════════════════════

class TravelUI {
    constructor(app) {
        this.app = app;
        this.mapInstance = null;
        this.mapLoaded = false;
        this.markers = [];
        this.polylines = [];
        this.currentPlan = null;
        this.currentStructured = null;

        this._STAGES = [
            { stage: 'parsing',     label: '解析旅行参数' },
            { stage: 'attractions', label: '搜索景点推荐' },
            { stage: 'route',       label: '规划路线' },
            { stage: 'hotels',      label: '搜索酒店' },
            { stage: 'food',        label: '推荐美食' },
            { stage: 'strategy',    label: '生成完整攻略' },
        ];

        this._initElements();
        this._bindEvents();
    }

    _initElements() {
        this.form           = document.getElementById('travelForm');
        this.destInput      = document.getElementById('destInput');
        this.startDateInput = document.getElementById('startDateInput');
        this.daysInput      = document.getElementById('daysInput');
        this.numPeopleInput = document.getElementById('numPeopleInput');
        this.budgetInput    = document.getElementById('budgetInput');
        this.prefTagsEl     = document.getElementById('prefTags');
        this.descInput      = document.getElementById('travelDescInput');
        this.submitBtn      = document.getElementById('travelSubmitBtn');
        this.progressEl     = document.getElementById('travelProgress');
        this.progressStages = document.getElementById('progressStages');
        this.resultEl       = document.getElementById('travelResult');
        this.dayCardsEl     = document.getElementById('dayCards');
        this.costSummaryEl  = document.getElementById('costSummary');
        this.replanBtn      = document.getElementById('replanBtn');
        this.printBtn       = document.getElementById('printPlanBtn');
        this.shareBtn       = document.getElementById('sharePlanBtn');
        this.shareOverlay   = document.getElementById('shareModalOverlay');
        this.shareUrlInput  = document.getElementById('shareUrlInput');
        this.copyBtn        = document.getElementById('copyShareUrlBtn');
        this.shareClose     = document.getElementById('shareModalClose');
        this.mapPlaceholder = document.getElementById('mapPlaceholder');
        this.destTitle      = document.getElementById('travelDestTitle');

        const today = new Date().toISOString().split('T')[0];
        if (this.startDateInput) this.startDateInput.value = today;
    }

    _bindEvents() {
        this.destInput?.addEventListener('input', () => this._updateSubmitState());
        this.prefTagsEl?.addEventListener('click', e => {
            if (e.target.classList.contains('pref-tag')) {
                e.target.classList.toggle('active');
            }
        });
        this.submitBtn?.addEventListener('click', () => this._startPlanning());
        this.replanBtn?.addEventListener('click', () => this._resetToForm());
        this.printBtn?.addEventListener('click', () => window.print());
        this.shareBtn?.addEventListener('click', () => this._generateShareLink());
        this.copyBtn?.addEventListener('click', () => this._copyShareUrl());
        this.shareClose?.addEventListener('click', () => this._closeShareModal());
        this.shareOverlay?.addEventListener('click', e => {
            if (e.target === this.shareOverlay) this._closeShareModal();
        });
    }

    _updateSubmitState() {
        if (this.submitBtn) {
            this.submitBtn.disabled = !this.destInput?.value.trim();
        }
    }

    _getSelectedPrefs() {
        return [...(this.prefTagsEl?.querySelectorAll('.pref-tag.active') || [])]
            .map(el => el.dataset.pref);
    }

    _buildRequestBody() {
        return {
            user_input: this.descInput?.value.trim() || '',
            trip_params: {
                destination: this.destInput?.value.trim() || '',
                start_date: this.startDateInput?.value || '',
                days: parseInt(this.daysInput?.value) || 3,
                num_people: parseInt(this.numPeopleInput?.value) || 2,
                budget: parseFloat(this.budgetInput?.value) || 3000,
                preferences: this._getSelectedPrefs(),
                language: 'zh',
            },
            session_id: this.app.sessionId,
        };
    }

    // ─── Progress ─────────────────────────────────────────────────────────────

    _showProgress() {
        if (this.form) this.form.style.display = 'none';
        if (this.progressEl) this.progressEl.style.display = '';
        if (this.resultEl) this.resultEl.style.display = 'none';
        if (this.printBtn) this.printBtn.style.display = 'none';
        if (this.shareBtn) this.shareBtn.style.display = 'none';

        if (this.progressStages) {
            this.progressStages.innerHTML = this._STAGES.map(s => `
                <div class="progress-stage" id="ps-${s.stage}">
                    <span class="stage-icon">⬜</span>
                    <span class="stage-label">${s.label}</span>
                </div>`).join('');
        }
    }

    _updateProgress(stage) {
        let found = false;
        for (const s of this._STAGES) {
            const el = document.getElementById(`ps-${s.stage}`);
            if (!el) continue;
            const icon = el.querySelector('.stage-icon');
            if (s.stage === stage) {
                el.className = 'progress-stage stage-active';
                icon.textContent = '⏳';
                found = true;
            } else if (!found) {
                el.className = 'progress-stage stage-done';
                icon.textContent = '✅';
            }
        }
    }

    _markAllStagesDone() {
        this._STAGES.forEach(s => {
            const el = document.getElementById(`ps-${s.stage}`);
            if (!el) return;
            el.className = 'progress-stage stage-done';
            el.querySelector('.stage-icon').textContent = '✅';
        });
    }

    // ─── Day Cards ────────────────────────────────────────────────────────────

    _showResult(structured) {
        if (this.progressEl) this.progressEl.style.display = 'none';
        if (this.resultEl) this.resultEl.style.display = '';
        if (this.printBtn) this.printBtn.style.display = '';
        if (this.shareBtn) this.shareBtn.style.display = '';

        if (!structured?.days?.length) {
            if (this.dayCardsEl) this.dayCardsEl.innerHTML = '<p style="color:#80868b;padding:12px">攻略已生成（无结构化预览）</p>';
            return;
        }

        // ── 酒店选项区块 ──────────────────────────────────────
        const hotelSectionId = 'hotelOptionsSection';
        let hotelSection = document.getElementById(hotelSectionId);
        if (!hotelSection) {
            hotelSection = document.createElement('div');
            hotelSection.id = hotelSectionId;
            this.dayCardsEl.parentNode.insertBefore(hotelSection, this.dayCardsEl);
        }
        hotelSection.innerHTML = this._renderHotelOptions(structured.hotel_options || []);

        // 酒店选择事件（选中 + 地图跳转）
        hotelSection.querySelectorAll('.hotel-option-card').forEach(card => {
            card.addEventListener('click', () => {
                hotelSection.querySelectorAll('.hotel-option-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                const idx = parseInt(card.dataset.idx);
                if (structured.hotel_options?.[idx]) {
                    this._updateSelectedHotel(structured.hotel_options[idx]);
                }
            });
        });

        // ── 行程卡片 ──────────────────────────────────────────
        if (this.dayCardsEl) {
            this.dayCardsEl.innerHTML = structured.days.map(d => this._renderDayCard(d)).join('');
            this.dayCardsEl.querySelectorAll('.day-card-header').forEach(header => {
                header.addEventListener('click', () => {
                    const card = header.closest('.day-card');
                    card.classList.toggle('expanded');
                    this._highlightDay(parseInt(card.dataset.day));
                });
            });
        }

        // ── 美食推荐表格 ──────────────────────────────────────
        const foodSectionId = 'foodRecommendSection';
        let foodSection = document.getElementById(foodSectionId);
        if (!foodSection) {
            foodSection = document.createElement('div');
            foodSection.id = foodSectionId;
            this.resultEl.appendChild(foodSection);
        }
        this._allFoods = structured.foods || [];
        this._foodSortAsc = null;
        foodSection.innerHTML = this._renderFoodTable(this._allFoods);
        this._bindFoodTableEvents(foodSection);

        // ── 费用摘要 ──────────────────────────────────────────
        const body = this._buildRequestBody();
        if (this.costSummaryEl) {
            this.costSummaryEl.textContent =
                `总预算 ¥${structured.total_cost} / ${structured.days.length}天 · ${body.trip_params.num_people}人`;
        }
    }

    _renderHotelOptions(options) {
        if (!options.length) return '';
        const hotelIcon = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4v16"/><path d="M2 8h18a2 2 0 0 1 2 2v10"/><path d="M2 17h20"/><path d="M6 8v9"/></svg>`;
        const pinIcon = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>`;
        const stars = n => Array(Math.min(n || 0, 5)).fill('<svg width="11" height="11" viewBox="0 0 24 24" fill="#F59E0B" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>').join('');
        return `
        <div class="hotel-options-section">
            <div class="section-title">${hotelIcon} 住宿推荐<span class="section-sub">全程入住同一家，点击选择</span></div>
            <div class="hotel-options-list">
                ${options.map((h, idx) => `
                <div class="hotel-option-card${idx === 0 ? ' selected' : ''}" data-idx="${idx}"
                     data-lng="${h.lng || ''}" data-lat="${h.lat || ''}">
                    <div class="hotel-card-header">
                        <span class="hotel-option-name">${this._esc(h.name)}</span>
                        ${h.price_per_night ? `<span class="hotel-price">¥${h.price_per_night}<span class="hotel-price-unit">/晚</span></span>` : ''}
                    </div>
                    <div class="hotel-meta-row">
                        ${h.stars ? `<span class="hotel-stars">${stars(h.stars)}</span>` : ''}
                        ${h.rating ? `<span class="hotel-rating">${h.rating} 分</span>` : ''}
                    </div>
                    ${h.address ? `<div class="hotel-option-addr">${pinIcon} ${this._esc(h.address)}</div>` : ''}
                    ${h.reason ? `<div class="hotel-option-reason">${this._esc(h.reason)}</div>` : ''}
                    ${h.amenities?.length ? `<div class="hotel-option-tags">${h.amenities.slice(0,5).map(a => `<span class="tag">${this._esc(a)}</span>`).join('')}</div>` : ''}
                </div>`).join('')}
            </div>
        </div>`;
    }

    _renderDayCard(day) {
        const date = day.date || `第${day.day}天`;
        const attrHtml = (day.attractions || []).map((a, i) => `
            <li class="attr-item">
                <span class="attr-num">${i + 1}</span>
                <div class="attr-detail">
                    <strong>${this._esc(a.name)}</strong>
                    ${a.ticket_price ? `<span class="attr-meta">门票 ${this._esc(String(a.ticket_price))}</span>` : ''}
                    ${a.duration ? `<span class="attr-meta">约 ${a.duration}</span>` : ''}
                    ${a.address ? `<div class="attr-addr">📍 ${this._esc(a.address)}</div>` : ''}
                    ${a.tip ? `<div class="attr-tip">💡 ${this._esc(a.tip)}</div>` : ''}
                </div>
            </li>`).join('');

        const routeHtml = day.route_note
            ? `<div class="route-note">🗺️ ${this._esc(day.route_note)}</div>`
            : '';

        return `<div class="day-card expanded" data-day="${day.day}">
            <div class="day-card-header">
                <span class="day-card-title">📅 第 ${day.day} 天 · ${this._esc(date)}</span>
                <span class="day-card-cost">${day.estimated_cost ? `预算 ¥${day.estimated_cost}` : ''}</span>
                <span class="day-card-toggle">▼</span>
            </div>
            <div class="day-card-body">
                <div id="route-day-${day.day}" class="route-steps-container">${routeHtml}</div>
                ${attrHtml ? `<ul class="attr-list">${attrHtml}</ul>` : '<p style="color:#80868b">暂无景点数据</p>'}
            </div>
        </div>`;
    }

    _renderFoodTable(foods) {
        if (!foods.length) return '';
        const diningIcon = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3zm0 0v7"/></svg>`;
        const sortIcon = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5h10M11 9h7M11 13h4"/><path d="M3 5l4 4-4 4"/></svg>`;
        const rows = foods.map((f, i) => this._foodRowHtml(f, i)).join('');
        return `
        <div class="food-table-section">
            <div class="food-table-header">
                <div class="section-title">${diningIcon} 美食推荐<span class="section-sub">共 ${foods.length} 家 · 已标注地图 · 点击行定位</span></div>
                <button class="food-sort-btn" id="foodSortBtn" title="按人均价格排序">
                    ${sortIcon}<span id="foodSortLabel">价格排序</span>
                </button>
            </div>
            <div class="food-table-wrap">
                <table class="food-table">
                    <thead>
                        <tr>
                            <th class="col-num">#</th>
                            <th class="col-name">餐厅</th>
                            <th class="col-cuisine">菜系</th>
                            <th class="col-price">人均</th>
                            <th class="col-sig">招牌菜</th>
                        </tr>
                    </thead>
                    <tbody id="foodTableBody">${rows}</tbody>
                </table>
            </div>
        </div>`;
    }

    _foodRowHtml(f, i) {
        const sig = Array.isArray(f.signature) ? f.signature.slice(0, 3).join('、') : (f.signature || '');
        const hasCoords = f.lng && f.lat;
        return `<tr class="food-row${hasCoords ? ' has-coords' : ''}" data-idx="${i}"
                    data-lng="${f.lng || ''}" data-lat="${f.lat || ''}"
                    title="${hasCoords ? '点击在地图上定位' : '暂无坐标'}">
            <td class="col-num"><span class="food-dot" style="background:${this._foodColor(i)}">${i + 1}</span></td>
            <td class="col-name">
                <div class="food-cell-name">${this._esc(f.name)}</div>
                ${f.address ? `<div class="food-cell-addr">${this._esc(f.address)}</div>` : ''}
            </td>
            <td class="col-cuisine"><span class="cuisine-tag">${this._esc(f.cuisine || '—')}</span></td>
            <td class="col-price">${f.avg_price ? `<span class="price-val">¥${f.avg_price}</span>` : '—'}</td>
            <td class="col-sig">${this._esc(sig) || '—'}</td>
        </tr>`;
    }

    _foodColor(idx) {
        const palette = ['#FF6B35','#E8572A','#FF8C00','#D4520A','#FF7043','#E64A19','#FF5722','#BF360C','#FF6D00','#E65100'];
        return palette[idx % palette.length];
    }

    _bindFoodTableEvents(container) {
        // 排序按钮
        const sortBtn = container.querySelector('#foodSortBtn');
        const label = container.querySelector('#foodSortLabel');
        if (sortBtn) {
            sortBtn.addEventListener('click', () => {
                this._foodSortAsc = this._foodSortAsc === null ? true : !this._foodSortAsc;
                const sorted = [...this._allFoods].sort((a, b) => {
                    const pa = a.avg_price || 0, pb = b.avg_price || 0;
                    return this._foodSortAsc ? pa - pb : pb - pa;
                });
                const tbody = container.querySelector('#foodTableBody');
                if (tbody) tbody.innerHTML = sorted.map((f, i) => this._foodRowHtml(f, i)).join('');
                if (label) label.textContent = this._foodSortAsc ? '价格↑' : '价格↓';
                sortBtn.classList.toggle('sort-active', true);
                this._rebindFoodRows(container);
            });
        }
        this._rebindFoodRows(container);
    }

    _rebindFoodRows(container) {
        container.querySelectorAll('.food-row.has-coords').forEach(row => {
            row.addEventListener('click', () => {
                const lng = parseFloat(row.dataset.lng);
                const lat = parseFloat(row.dataset.lat);
                const idx = parseInt(row.dataset.idx);
                // 高亮行
                container.querySelectorAll('.food-row').forEach(r => r.classList.remove('active'));
                row.classList.add('active');
                // 地图定位
                if (this.mapInstance && lng && lat) {
                    this.mapInstance.setCenter([lng, lat]);
                    this.mapInstance.setZoom(16);
                    // 打开对应 InfoWindow
                    if (this.foodInfoWindows?.[idx]) {
                        this.foodInfoWindows[idx].open(this.mapInstance, this.foodMarkers[idx].getPosition());
                    }
                }
            });
        });
    }

    _updateSelectedHotel(hotel) {
        this._clearHotelMarkers();
        if (hotel.lng && hotel.lat) this._addHotelMapMarker(hotel);
        // 地图跳转
        if (this.mapInstance && hotel.lng && hotel.lat) {
            this.mapInstance.setCenter([hotel.lng, hotel.lat]);
            this.mapInstance.setZoom(14);
        }
    }

    _esc(str) {
        if (!str) return '';
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    _resetToForm() {
        this.currentPlan = null;
        this.currentStructured = null;
        if (this.resultEl) this.resultEl.style.display = 'none';
        if (this.form) this.form.style.display = '';
        if (this.printBtn) this.printBtn.style.display = 'none';
        if (this.shareBtn) this.shareBtn.style.display = 'none';
        if (this.destTitle) this.destTitle.textContent = '旅游规划工作台';
        this._clearMap();
    }

    // ─── Planning Flow ────────────────────────────────────────────────────────

    async startPlanning() {
        this._showProgress();
        this._clearMap();
        await this._loadMap();

        const body = this._buildRequestBody();
        if (this.destTitle) {
            this.destTitle.textContent = `正在规划 · ${body.trip_params.destination}`;
        }

        try {
            const resp = await fetch('/api/travel/plan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                const lines = buf.split('\n');
                buf = lines.pop() || '';
                for (const line of lines) {
                    if (!line.startsWith('data:')) continue;
                    try {
                        const event = JSON.parse(line.slice(5).trim());
                        this._handleEvent(event);
                    } catch (_) {}
                }
            }
        } catch (e) {
            this._showError(e.message);
        }
    }

    _startPlanning() { this.startPlanning(); }

    _handleEvent(event) {
        if (event.type === 'progress') {
            this._updateProgress(event.stage);
            if (event.stage === 'attractions' && event.attractions?.length) {
                this._addMarkers(event.attractions, 'attraction');
            }
        } else if (event.type === 'complete') {
            this.currentPlan = event.final_plan;
            this.currentStructured = event.structured_plan;
            this._markAllStagesDone();
            const dest = this._buildRequestBody().trip_params.destination;
            if (this.destTitle) this.destTitle.textContent = `${dest} 攻略`;
            setTimeout(() => {
                this._showResult(this.currentStructured);
                if (this.currentStructured) {
                    this._renderMapFromStructured(this.currentStructured);
                }
            }, 600);
        } else if (event.type === 'error') {
            this._showError(event.message);
        }
    }

    _showError(msg) {
        if (this.progressEl) this.progressEl.style.display = 'none';
        if (this.form) this.form.style.display = '';
        alert(`规划失败：${msg}`);
    }

    // ─── Amap Map ─────────────────────────────────────────────────────────────

    async _loadMap() {
        if (this.mapLoaded) return;
        try {
            const resp = await fetch('/api/travel/map-key');
            if (!resp.ok) return;
            const { key, security_code } = await resp.json();
            if (!key) return;

            // JS API 2.0 必须在加载 SDK 前设置安全密钥
            if (security_code) {
                window._AMapSecurityConfig = { securityJsCode: security_code };
            }

            await new Promise((resolve, reject) => {
                const s = document.createElement('script');
                s.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}&plugin=AMap.Polyline,AMap.Driving,AMap.Transfer,AMap.Walking,AMap.Cycling,AMap.Weather,AMap.PlaceSearch`;
                s.onload = resolve;
                s.onerror = reject;
                document.head.appendChild(s);
            });

            this.mapInstance = new window.AMap.Map('amapContainer', {
                zoom: 11,
                center: [104.065735, 30.659462],
            });
            this.mapLoaded = true;
            if (this.mapPlaceholder) this.mapPlaceholder.style.display = 'none';
        } catch (e) {
            console.warn('[TravelUI] 地图加载失败:', e);
        }
    }

    _clearMap() {
        if (!this.mapInstance) return;
        this.markers.forEach(m => m.setMap(null));
        this.polylines.forEach(p => p.setMap(null));
        (this.foodMarkers || []).forEach(m => m.setMap(null));
        (this.hotelMarkers || []).forEach(m => m.setMap(null));
        (this.routeRenderers || []).forEach(r => { try { r.clear(); } catch (_) {} });
        this.markers = [];
        this.polylines = [];
        this.foodMarkers = [];
        this.foodInfoWindows = [];
        this.hotelMarkers = [];
        this.routeRenderers = [];
    }

    // SSE 进度阶段的临时景点标记（蓝色默认图钉，被 _renderMapFromStructured 覆盖）
    _addMarkers(items, type) {
        if (!this.mapInstance || !window.AMap) return;
        items.forEach(item => {
            if (!item.lng || !item.lat) return;
            const marker = new window.AMap.Marker({
                position: [item.lng, item.lat],
                title: item.name || '',
                map: this.mapInstance,
                icon: new window.AMap.Icon({
                    image: 'https://webapi.amap.com/theme/v1.3/markers/n/mark_b.png',
                    size: new window.AMap.Size(19, 31),
                    imageSize: new window.AMap.Size(19, 31),
                }),
            });
            this.markers.push(marker);
        });
    }

    _addHotelMapMarker(hotel) {
        if (!this.mapInstance || !window.AMap || !hotel?.lng || !hotel?.lat) return;
        const svgContent = `<div style="
            width:38px;height:38px;background:#1a73e8;border-radius:50%;
            display:flex;align-items:center;justify-content:center;
            box-shadow:0 3px 10px rgba(26,115,232,0.5);border:2.5px solid #fff;
            cursor:pointer;transition:transform 0.15s
        ">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 4v16"/><path d="M2 8h18a2 2 0 0 1 2 2v10"/><path d="M2 17h20"/><path d="M6 8v9"/>
            </svg>
        </div>`;
        const marker = new window.AMap.Marker({
            position: [hotel.lng, hotel.lat],
            map: this.mapInstance,
            content: svgContent,
            offset: new window.AMap.Pixel(-19, -19),
            zIndex: 200,
        });
        const priceStr = hotel.price_per_night ? `¥${hotel.price_per_night}/晚` : '';
        const infoHtml = `<div style="padding:10px 14px;font-size:13px;min-width:160px">
            <div style="font-weight:600;color:#1a73e8;margin-bottom:4px">${hotel.name || '酒店'}</div>
            ${hotel.stars ? `<div style="color:#F59E0B;font-size:12px">${'★'.repeat(Math.min(hotel.stars,5))} ${hotel.rating ? hotel.rating + ' 分' : ''}</div>` : ''}
            ${priceStr ? `<div style="color:#188038;font-weight:500;margin-top:4px">${priceStr}</div>` : ''}
            ${hotel.address ? `<div style="color:#80868b;font-size:12px;margin-top:4px">${hotel.address}</div>` : ''}
        </div>`;
        const info = new window.AMap.InfoWindow({ content: infoHtml, offset: new window.AMap.Pixel(0, -38) });
        marker.on('click', () => info.open(this.mapInstance, marker.getPosition()));
        this.hotelMarkers = this.hotelMarkers || [];
        this.hotelMarkers.push(marker);
    }

    _addFoodMapMarkers(foods) {
        if (!this.mapInstance || !window.AMap) return;
        this.foodMarkers = [];
        this.foodInfoWindows = [];
        foods.forEach((f, idx) => {
            if (!f.lng || !f.lat) return;
            const bg = this._foodColor(idx);
            const svgContent = `<div style="
                width:34px;height:34px;background:${bg};border-radius:50%;
                display:flex;align-items:center;justify-content:center;
                box-shadow:0 3px 8px rgba(255,107,53,0.45);border:2.5px solid #fff;
                cursor:pointer;transition:transform 0.15s
            ">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/>
                    <path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3zm0 0v7"/>
                </svg>
            </div>`;
            const marker = new window.AMap.Marker({
                position: [f.lng, f.lat],
                map: this.mapInstance,
                content: svgContent,
                offset: new window.AMap.Pixel(-17, -17),
                zIndex: 150,
            });
            const sig = Array.isArray(f.signature) ? f.signature.slice(0,3).join('、') : (f.signature || '');
            const infoHtml = `<div style="padding:10px 14px;font-size:13px;min-width:150px;max-width:220px">
                <div style="font-weight:600;color:#FF6B35;margin-bottom:4px">${f.name || '餐厅'}</div>
                ${f.cuisine ? `<span style="background:#fff3ee;color:#FF6B35;font-size:11px;padding:1px 6px;border-radius:8px">${f.cuisine}</span>` : ''}
                ${f.avg_price ? `<span style="float:right;color:#188038;font-weight:600">¥${f.avg_price}/人</span>` : ''}
                ${sig ? `<div style="color:#5f6368;font-size:12px;margin-top:6px">招牌：${sig}</div>` : ''}
                ${f.address ? `<div style="color:#80868b;font-size:12px;margin-top:4px">${f.address}</div>` : ''}
            </div>`;
            const infoWin = new window.AMap.InfoWindow({ content: infoHtml, offset: new window.AMap.Pixel(0, -34) });
            marker.on('click', () => infoWin.open(this.mapInstance, marker.getPosition()));
            this.foodMarkers.push(marker);
            this.foodInfoWindows.push(infoWin);
        });
    }

    _renderMapFromStructured(structured) {
        if (!this.mapInstance || !window.AMap || !structured?.days) return;

        const COLORS = ['#4A90E2', '#E2574A', '#FF8C00', '#9B59B6', '#1ABC9C', '#F39C12', '#E91E63'];
        const allLngLat = [];

        // ── 酒店标注（选中的第一家）────────────────────────────
        const hotel = structured.selected_hotel || structured.hotel_options?.[0];
        if (hotel?.lng && hotel?.lat) {
            this._addMarkers([hotel], 'hotel');
            allLngLat.push([hotel.lng, hotel.lat]);
        }

        // ── 每天景点 + 路线折线（酒店→景点→酒店）──────────────
        structured.days.forEach((day, idx) => {
            const pts = [];

            // 从酒店出发
            if (hotel?.lng && hotel?.lat) pts.push([hotel.lng, hotel.lat]);

            (day.attractions || []).forEach(a => {
                if (a.lng && a.lat) {
                    pts.push([a.lng, a.lat]);
                    allLngLat.push([a.lng, a.lat]);
                }
            });

            // 返回酒店
            if (hotel?.lng && hotel?.lat && pts.length > 1) pts.push([hotel.lng, hotel.lat]);

            if (pts.length > 2) {
                const poly = new window.AMap.Polyline({
                    path: pts.map(p => new window.AMap.LngLat(p[0], p[1])),
                    strokeColor: COLORS[idx % COLORS.length],
                    strokeWeight: 3,
                    strokeOpacity: 0.85,
                    strokeDasharray: idx === 0 ? null : [10, 5],
                    map: this.mapInstance,
                });
                this.polylines.push(poly);
            }
        });

        // ── 景点标记（带序号）──────────────────────────────────
        structured.days.forEach((day, dayIdx) => {
            (day.attractions || []).forEach((a, attrIdx) => {
                if (!a.lng || !a.lat || !window.AMap) return;
                const color = COLORS[dayIdx % COLORS.length];
                const marker = new window.AMap.Marker({
                    position: [a.lng, a.lat],
                    map: this.mapInstance,
                    content: `<div style="background:${color};color:#fff;border-radius:50%;width:24px;height:24px;line-height:24px;text-align:center;font-size:12px;font-weight:bold;box-shadow:0 2px 4px rgba(0,0,0,.3)">${attrIdx + 1}</div>`,
                    offset: new window.AMap.Pixel(-12, -12),
                });
                const infoContent = `<div style="padding:8px 12px;font-size:13px;max-width:200px">
                    <b>Day${day.day} · ${a.name}</b>
                    ${a.address ? `<br><span style="color:#80868b;font-size:12px">📍 ${a.address}</span>` : ''}
                    ${a.tip ? `<br><span style="color:#f29900;font-size:12px">💡 ${a.tip}</span>` : ''}
                </div>`;
                const info = new window.AMap.InfoWindow({ content: infoContent, offset: new window.AMap.Pixel(0, -24) });
                marker.on('click', () => info.open(this.mapInstance, marker.getPosition()));
                this.markers.push(marker);
            });
        });

        // ── 自动缩放到全部景点范围 ─────────────────────────────
        if (allLngLat.length) {
            const lngs = allLngLat.map(p => p[0]);
            const lats = allLngLat.map(p => p[1]);
            this.mapInstance.setBounds(new window.AMap.Bounds(
                new window.AMap.LngLat(Math.min(...lngs), Math.min(...lats)),
                new window.AMap.LngLat(Math.max(...lngs), Math.max(...lats)),
            ));
        }

        // ── 美食标注（常驻，无需切换）──────────────────────────
        this._addFoodMapMarkers(structured.foods || []);

        // ── 天气 + 前端坐标补全 + 路线规划（异步）────────────────
        const dest = this._buildRequestBody().trip_params.destination;
        this._fetchWeather(dest);
        // 先做前端坐标补全，再绘制路线（避免路线空缺）
        this._geocodeMissingAndPlan(structured, dest);
    }

    _clearHotelMarkers() {
        (this.hotelMarkers || []).forEach(m => m.setMap(null));
        this.hotelMarkers = [];
    }

    // ─── 天气 ──────────────────────────────────────────────────────────────────

    _fetchWeather(city) {
        if (!window.AMap?.Weather) return;
        const weather = new window.AMap.Weather();
        weather.getLive(city, (err, live) => {
            if (err || !live) return;
            weather.getForecast(city, (err2, forecast) => {
                this._renderWeatherWidget(live, err2 ? null : forecast);
            });
        });
    }

    _renderWeatherWidget(live, forecast) {
        const el = document.getElementById('weatherWidget');
        if (!el) return;

        const condIcon = cond => {
            if (!cond) return '';
            if (cond.includes('晴')) return '<span class="wi-sunny">☀</span>';
            if (cond.includes('云') || cond.includes('阴')) return '<span class="wi-cloudy">⛅</span>';
            if (cond.includes('雨')) return '<span class="wi-rainy">🌧</span>';
            if (cond.includes('雪')) return '<span class="wi-snow">❄</span>';
            if (cond.includes('雾') || cond.includes('霾')) return '<span class="wi-fog">🌫</span>';
            return '<span class="wi-cloud">☁</span>';
        };

        const forecastHtml = forecast?.forecasts?.slice(0, 3).map(f => `
            <div class="wf-item">
                <div class="wf-day">${f.week === '1' ? '周一' : f.week === '2' ? '周二' : f.week === '3' ? '周三' : f.week === '4' ? '周四' : f.week === '5' ? '周五' : f.week === '6' ? '周六' : '周日'}</div>
                <div class="wf-icon">${condIcon(f.dayWeather)}</div>
                <div class="wf-temp">${f.nightTemp}°~${f.dayTemp}°</div>
            </div>`).join('') || '';

        el.innerHTML = `
            <div class="weather-live">
                <div class="wl-left">
                    <span class="wl-icon">${condIcon(live.weather)}</span>
                    <div>
                        <div class="wl-city">${this._esc(live.city || '')}</div>
                        <div class="wl-cond">${this._esc(live.weather || '')}</div>
                    </div>
                </div>
                <div class="wl-temp">${live.temperature}°<span class="wl-unit">C</span></div>
            </div>
            <div class="weather-detail">
                ${live.windDirection ? `<span>${this._esc(live.windDirection)}风 ${live.windPower || ''}级</span>` : ''}
                ${live.humidity ? `<span>湿度 ${live.humidity}%</span>` : ''}
            </div>
            ${forecastHtml ? `<div class="weather-forecast">${forecastHtml}</div>` : ''}`;
        el.style.display = '';
    }

    // ─── 智能路线规划 ──────────────────────────────────────────────────────────

    async _planDayRoutes(structured, city) {
        if (!this.mapInstance || !window.AMap) return;
        const hotel = structured.selected_hotel || structured.hotel_options?.[0];

        // 清除简单折线，由实际路线替代
        this.polylines.forEach(p => p.setMap(null));
        this.polylines = [];
        this.routeRenderers = [];

        const COLORS = ['#4A90E2', '#E2574A', '#FF8C00', '#9B59B6', '#1ABC9C', '#F39C12', '#E91E63'];

        for (let dayIdx = 0; dayIdx < structured.days.length; dayIdx++) {
            const day = structured.days[dayIdx];
            await this._planOneDayRoute(day, hotel, city, COLORS[dayIdx % COLORS.length], dayIdx);
        }
    }

    async _planOneDayRoute(day, hotel, city, color, dayIdx) {
        const waypoints = [];
        if (hotel?.lng && hotel?.lat) waypoints.push({ lng: hotel.lng, lat: hotel.lat, name: hotel.name || '酒店' });
        for (const a of day.attractions || []) {
            if (a.lng && a.lat) waypoints.push({ lng: a.lng, lat: a.lat, name: a.name });
        }
        if (hotel?.lng && hotel?.lat && waypoints.length > 1) {
            waypoints.push({ lng: hotel.lng, lat: hotel.lat, name: hotel.name || '酒店' });
        }
        if (waypoints.length < 2) return;

        // ── 每段距离 + 交通方式 ──────────────────────────────
        const segments = [];
        for (let i = 0; i < waypoints.length - 1; i++) {
            const distKm = this._distanceKm(
                [waypoints[i].lng, waypoints[i].lat],
                [waypoints[i+1].lng, waypoints[i+1].lat]
            );
            segments.push({ from: waypoints[i], to: waypoints[i+1], distKm });
        }

        // ── 查询各段交通方式（中等距离查地铁）────────────────
        const modes = await Promise.all(segments.map(seg => this._resolveTransport(seg, city)));

        // ── 更新日程卡片路线信息 ──────────────────────────────
        this._updateDayCardRoute(day.day, waypoints, modes);

        // ── 用 Driving API 获取实际路线并用自定义色渲染 ──────
        await this._renderActualRoute(waypoints, color);
    }

    async _resolveTransport(seg, city) {
        const dist = seg.distKm;
        if (dist < 1.5) {
            return { mode: 'walk', label: '步行', mins: Math.ceil(dist * 1000 / 80), distKm: dist };
        }
        if (dist < 4) {
            return { mode: 'cycle', label: '骑行', mins: Math.ceil(dist * 1000 / 200), distKm: dist };
        }
        // 中等距离：查询公交/地铁
        if (dist < 30 && window.AMap?.Transfer) {
            const result = await this._queryTransit(seg, city);
            if (result) return result;
        }
        // 远距离或无公交
        return { mode: 'taxi', label: '打车', mins: Math.ceil(dist * 60 / 40), distKm: dist };
    }

    _queryTransit(seg, city) {
        return new Promise(resolve => {
            try {
                const transfer = new window.AMap.Transfer({
                    city,
                    policy: window.AMap.TransferPolicy ? window.AMap.TransferPolicy.LEAST_TIME : 0,
                    hideMarkers: true,
                });
                const timeout = setTimeout(() => resolve(null), 4000);
                transfer.search(
                    new window.AMap.LngLat(seg.from.lng, seg.from.lat),
                    new window.AMap.LngLat(seg.to.lng, seg.to.lat),
                    (status, result) => {
                        clearTimeout(timeout);
                        if (status !== 'complete' || !result?.plans?.length) { resolve(null); return; }
                        const plan = result.plans[0];
                        const hasSubway = plan.segments?.some(s =>
                            s.transit?.lines?.some(l => l.type === '地铁' || l.type === 'Subway')
                        );
                        const mins = Math.ceil((plan.time || 0) / 60);
                        resolve({
                            mode: hasSubway ? 'metro' : 'bus',
                            label: hasSubway ? '乘地铁' : '乘公交',
                            mins: mins || Math.ceil(seg.distKm * 60 / 25),
                            distKm: seg.distKm,
                        });
                    }
                );
            } catch (_) { resolve(null); }
        });
    }

    async _renderActualRoute(waypoints, color) {
        const validPts = waypoints.filter(p => p.lng && p.lat);
        if (validPts.length < 2) return;

        if (!window.AMap?.Driving) {
            this._drawFallbackPolyline(validPts, color);
            return;
        }

        return new Promise(resolve => {
            try {
                const driving = new window.AMap.Driving({ autoFitView: false, policy: 0 });
                const origin = new window.AMap.LngLat(validPts[0].lng, validPts[0].lat);
                const dest   = new window.AMap.LngLat(validPts[validPts.length - 1].lng, validPts[validPts.length - 1].lat);
                const via    = validPts.slice(1, -1).map(p => new window.AMap.LngLat(p.lng, p.lat));
                const timeout = setTimeout(() => {
                    this._drawFallbackPolyline(validPts, color);
                    resolve();
                }, 7000);

                driving.search(origin, dest, { waypoints: via }, (status, result) => {
                    clearTimeout(timeout);
                    let drawn = false;
                    if (status === 'complete' && result?.routes?.[0]?.steps) {
                        const path = [];
                        result.routes[0].steps.forEach(s => { if (s.path) path.push(...s.path); });
                        if (path.length > 1) {
                            const poly = new window.AMap.Polyline({
                                path,
                                strokeColor: color,
                                strokeWeight: 4,
                                strokeOpacity: 0.85,
                                map: this.mapInstance,
                                zIndex: 50,
                            });
                            this.polylines.push(poly);
                            drawn = true;
                        }
                    }
                    if (!drawn) this._drawFallbackPolyline(validPts, color);
                    resolve();
                });
                this.routeRenderers.push(driving);
            } catch (_) {
                this._drawFallbackPolyline(validPts, color);
                resolve();
            }
        });
    }

    _drawFallbackPolyline(waypoints, color) {
        const validPts = waypoints.filter(p => p.lng && p.lat);
        if (!this.mapInstance || !window.AMap || validPts.length < 2) return;
        const poly = new window.AMap.Polyline({
            path: validPts.map(p => new window.AMap.LngLat(p.lng, p.lat)),
            strokeColor: color,
            strokeWeight: 3,
            strokeOpacity: 0.55,
            strokeStyle: 'dashed',
            strokeDasharray: [12, 6],
            map: this.mapInstance,
            zIndex: 45,
        });
        this.polylines.push(poly);
    }

    // ─── 前端坐标补全 + 路线重触发 ─────────────────────────────────────────────

    async _geocodeMissingAndPlan(structured, city) {
        await this._geocodeMissing(structured, city);
        // 补全后重新添加地图标注（增量，不清除已有的）
        this._addMissingMarkers(structured);
        // 再规划路线
        await this._planDayRoutes(structured, city);
    }

    async _geocodeMissing(structured, city) {
        if (!window.AMap?.PlaceSearch) return;

        const search = name => new Promise(resolve => {
            try {
                const ps = new window.AMap.PlaceSearch({ city, citylimit: true, pageSize: 1 });
                const t = setTimeout(() => resolve(null), 3000);
                ps.search(name, (status, result) => {
                    clearTimeout(t);
                    if (status === 'complete' && result?.poiList?.pois?.[0]) {
                        const loc = result.poiList.pois[0].location;
                        resolve({ lng: loc.getLng(), lat: loc.getLat() });
                    } else resolve(null);
                });
            } catch (_) { resolve(null); }
        });

        const tasks = [];

        // 酒店
        for (const h of structured.hotel_options || []) {
            if (!h.lng && h.name) tasks.push(search(h.name).then(c => { if (c) { h.lng = c.lng; h.lat = c.lat; } }));
        }
        if (structured.selected_hotel && !structured.selected_hotel.lng) {
            const src = (structured.hotel_options || []).find(h => h.name === structured.selected_hotel.name);
            if (src?.lng) { structured.selected_hotel.lng = src.lng; structured.selected_hotel.lat = src.lat; }
        }

        // 景点
        for (const day of structured.days || []) {
            for (const a of day.attractions || []) {
                if (!a.lng && a.name) tasks.push(search(a.name).then(c => { if (c) { a.lng = c.lng; a.lat = c.lat; } }));
            }
        }

        // 美食
        for (const f of structured.foods || []) {
            if (!f.lng && f.name) tasks.push(search(f.name).then(c => { if (c) { f.lng = c.lng; f.lat = c.lat; } }));
        }

        await Promise.all(tasks);

        // 同步 selected_hotel 坐标（可能在上面酒店循环中被补全）
        if (structured.selected_hotel && !structured.selected_hotel.lng) {
            const h0 = structured.hotel_options?.[0];
            if (h0?.lng) { structured.selected_hotel.lng = h0.lng; structured.selected_hotel.lat = h0.lat; }
        }
    }

    _addMissingMarkers(structured) {
        if (!this.mapInstance || !window.AMap) return;

        // 补全后的酒店标注（若之前未标注）
        const hotel = structured.selected_hotel || structured.hotel_options?.[0];
        const alreadyHasHotel = (this.hotelMarkers || []).length > 0;
        if (!alreadyHasHotel && hotel?.lng && hotel?.lat) {
            this._addHotelMapMarker(hotel);
        }

        // 补全后的景点标注（只加之前跳过的）
        const COLORS = ['#4A90E2', '#E2574A', '#FF8C00', '#9B59B6', '#1ABC9C', '#F39C12', '#E91E63'];
        const existingPositions = new Set(
            this.markers.map(m => { const p = m.getPosition(); return p ? `${p.getLng().toFixed(4)},${p.getLat().toFixed(4)}` : ''; })
        );
        (structured.days || []).forEach((day, dayIdx) => {
            (day.attractions || []).forEach((a, attrIdx) => {
                if (!a.lng || !a.lat) return;
                const key = `${a.lng.toFixed(4)},${a.lat.toFixed(4)}`;
                if (existingPositions.has(key)) return;
                const color = COLORS[dayIdx % COLORS.length];
                const marker = new window.AMap.Marker({
                    position: [a.lng, a.lat],
                    map: this.mapInstance,
                    content: `<div style="background:${color};color:#fff;border-radius:50%;width:24px;height:24px;line-height:24px;text-align:center;font-size:12px;font-weight:bold;box-shadow:0 2px 4px rgba(0,0,0,.3)">${attrIdx + 1}</div>`,
                    offset: new window.AMap.Pixel(-12, -12),
                    zIndex: 100,
                });
                const infoContent = `<div style="padding:8px 12px;font-size:13px;max-width:200px">
                    <b>Day${day.day} · ${a.name}</b>
                    ${a.address ? `<br><span style="color:#80868b;font-size:12px">📍 ${a.address}</span>` : ''}
                    ${a.tip ? `<br><span style="color:#f29900;font-size:12px">💡 ${a.tip}</span>` : ''}
                </div>`;
                const info = new window.AMap.InfoWindow({ content: infoContent, offset: new window.AMap.Pixel(0, -24) });
                marker.on('click', () => info.open(this.mapInstance, marker.getPosition()));
                this.markers.push(marker);
                existingPositions.add(key);
            });
        });

        // 补全后的美食标注
        const existingFoodPositions = new Set(
            (this.foodMarkers || []).map(m => { const p = m.getPosition(); return p ? `${p.getLng().toFixed(4)},${p.getLat().toFixed(4)}` : ''; })
        );
        (structured.foods || []).forEach((f, idx) => {
            if (!f.lng || !f.lat) return;
            const key = `${f.lng.toFixed(4)},${f.lat.toFixed(4)}`;
            if (existingFoodPositions.has(key)) return;
            const bg = this._foodColor(idx);
            const svgContent = `<div style="width:34px;height:34px;background:${bg};border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 3px 8px rgba(255,107,53,0.45);border:2.5px solid #fff;cursor:pointer">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/>
                    <path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3zm0 0v7"/>
                </svg></div>`;
            const marker = new window.AMap.Marker({
                position: [f.lng, f.lat],
                map: this.mapInstance,
                content: svgContent,
                offset: new window.AMap.Pixel(-17, -17),
                zIndex: 150,
            });
            const sig = Array.isArray(f.signature) ? f.signature.slice(0, 3).join('、') : (f.signature || '');
            const infoHtml = `<div style="padding:10px 14px;font-size:13px;min-width:150px;max-width:220px">
                <div style="font-weight:600;color:#FF6B35;margin-bottom:4px">${f.name || '餐厅'}</div>
                ${f.cuisine ? `<span style="background:#fff3ee;color:#FF6B35;font-size:11px;padding:1px 6px;border-radius:8px">${f.cuisine}</span>` : ''}
                ${f.avg_price ? `<span style="float:right;color:#188038;font-weight:600">¥${f.avg_price}/人</span>` : ''}
                ${sig ? `<div style="color:#5f6368;font-size:12px;margin-top:6px">招牌：${sig}</div>` : ''}
                ${f.address ? `<div style="color:#80868b;font-size:12px;margin-top:4px">${f.address}</div>` : ''}
            </div>`;
            const infoWin = new window.AMap.InfoWindow({ content: infoHtml, offset: new window.AMap.Pixel(0, -34) });
            marker.on('click', () => infoWin.open(this.mapInstance, marker.getPosition()));
            this.foodMarkers.push(marker);
            this.foodInfoWindows.push(infoWin);
        });
    }

    _distanceKm(pt1, pt2) {
        const R = 6371;
        const dLat = (pt2[1] - pt1[1]) * Math.PI / 180;
        const dLng = (pt2[0] - pt1[0]) * Math.PI / 180;
        const a = Math.sin(dLat/2)**2 +
                  Math.cos(pt1[1]*Math.PI/180) * Math.cos(pt2[1]*Math.PI/180) *
                  Math.sin(dLng/2)**2;
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    }

    _updateDayCardRoute(dayNum, waypoints, modes) {
        const el = document.getElementById(`route-day-${dayNum}`);
        if (!el) return;

        const modeIconHtml = mode => {
            const icons = {
                walk:  `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="4" r="2"/><path d="M9 22V12l-2-5h10l-2 5v10"/><path d="M9 14h6"/></svg>`,
                cycle: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="5.5" cy="17.5" r="3.5"/><circle cx="18.5" cy="17.5" r="3.5"/><path d="M15 6a1 1 0 0 0 0-2h-3l-3 9 2 2 1-4 2 3h3"/><circle cx="15" cy="5" r="1"/></svg>`,
                metro: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="5" y="2" width="14" height="18" rx="3"/><circle cx="9" cy="16" r="1" fill="currentColor"/><circle cx="15" cy="16" r="1" fill="currentColor"/><path d="M9 6h6M9 10h6"/><path d="M7 20l-2 2m12-2l2 2"/></svg>`,
                bus:   `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="3" width="18" height="14" rx="2"/><path d="M3 9h18M3 14h18M8 20v-3m8 3v-3"/><circle cx="7" cy="17" r="1" fill="currentColor"/><circle cx="17" cy="17" r="1" fill="currentColor"/></svg>`,
                taxi:  `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 17H3v-5l2-5h14l2 5v5h-2"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/><path d="M9 8v4"/></svg>`,
            };
            return icons[mode] || '';
        };

        const modeColors = { walk:'#188038', cycle:'#1a73e8', metro:'#9C27B0', bus:'#FF6B35', taxi:'#F59E0B' };

        let html = '<div class="route-steps">';
        for (let i = 0; i < modes.length; i++) {
            const m = modes[i];
            const color = modeColors[m.mode] || '#5f6368';
            const distStr = m.distKm < 1 ? `${Math.round(m.distKm * 1000)}m` : `${m.distKm.toFixed(1)}km`;
            html += `
            <div class="route-step">
                <span class="rs-node">${this._esc(waypoints[i]?.name || '')}</span>
                <div class="rs-seg" style="color:${color}">
                    ${modeIconHtml(m.mode)}
                    <span>${m.label} · ${distStr} · 约${m.mins}分钟</span>
                </div>
            </div>`;
        }
        if (waypoints.length) {
            html += `<span class="rs-node">${this._esc(waypoints[waypoints.length-1]?.name || '')}</span>`;
        }
        html += '</div>';
        el.innerHTML = html;
    }

    _highlightDay(dayNum) {
        if (!this.polylines.length) return;
        this.polylines.forEach((poly, idx) => {
            const isSelected = idx + 1 === dayNum;
            poly.setOptions({
                strokeOpacity: isSelected ? 1 : 0.2,
                strokeWeight: isSelected ? 5 : 2,
            });
        });
        document.querySelectorAll('.day-card').forEach(card => {
            card.classList.toggle('highlight', parseInt(card.dataset.day) === dayNum);
        });
    }

    // ─── Share & Export ───────────────────────────────────────────────────────

    async _generateShareLink() {
        if (!this.currentPlan && !this.currentStructured) return;
        try {
            const resp = await fetch('/api/travel/share', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    plan: this.currentPlan || '',
                    structured_plan: this.currentStructured || {},
                }),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            if (this.shareUrlInput) this.shareUrlInput.value = data.url;
            if (this.shareOverlay) this.shareOverlay.style.display = 'flex';
        } catch (e) {
            alert('生成分享链接失败：' + e.message);
        }
    }

    async _copyShareUrl() {
        const url = this.shareUrlInput?.value;
        if (!url) return;
        try {
            await navigator.clipboard.writeText(url);
            if (this.copyBtn) {
                this.copyBtn.textContent = '已复制 ✓';
                setTimeout(() => { if (this.copyBtn) this.copyBtn.textContent = '复制'; }, 2000);
            }
        } catch (_) {
            this.shareUrlInput?.select();
        }
    }

    _closeShareModal() {
        if (this.shareOverlay) this.shareOverlay.style.display = 'none';
    }

    async loadSharedPlan(shareId) {
        try {
            const resp = await fetch(`/api/travel/share/${encodeURIComponent(shareId)}`);
            if (!resp.ok) throw new Error('分享链接不存在或已失效');
            const data = await resp.json();
            this.currentPlan = data.plan;
            this.currentStructured = data.structured_plan;

            if (this.form) this.form.style.display = 'none';
            const toolbar = document.getElementById('travelToolbar');
            if (toolbar) toolbar.style.display = 'none';

            this._showResult(this.currentStructured);
            await this._loadMap();
            if (this.currentStructured) this._renderMapFromStructured(this.currentStructured);

            const dest = this.currentStructured?.days?.[0]?.attractions?.[0]?.name || '共享攻略';
            if (this.destTitle) this.destTitle.textContent = dest;
        } catch (e) {
            alert(e.message);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const app = new SuperBizAgentApp();
    window.__app = app;

    const shareId = new URLSearchParams(window.location.search).get('share');
    if (shareId) {
        app.switchAppMode('travel');
        app.travelUI.loadSharedPlan(shareId);
    }
});
