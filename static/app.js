// 智能旅游助手 — 双模式前端
class SuperBizAgentApp {
    constructor() {
        this.apiBaseUrl = '/api';
        this.appMode = 'chat';       // 'chat' | 'travel'
        this.currentMode = 'quick';  // chat 子模式：'quick' | 'stream'
        this.sessionId = this.generateSessionId();
        this.isStreaming = false;
        this.currentChatHistory = [];
        this.chatHistories = this.loadChatHistories();
        this.isCurrentChatFromHistory = false;

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
        this.updateUI();
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
        this.showNotification(`已切换到${mode === 'quick' ? '快速' : '流式'}模式`, 'info');
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
            this.currentModeText.textContent = this.currentMode === 'quick' ? '快速' : '流式';
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

        if (this.dayCardsEl) {
            this.dayCardsEl.innerHTML = structured.days.map(d => this._renderDayCard(d)).join('');
            this.dayCardsEl.querySelectorAll('.day-card-header').forEach(header => {
                header.addEventListener('click', () => {
                    const card = header.closest('.day-card');
                    card.classList.toggle('expanded');
                    const dayNum = parseInt(card.dataset.day);
                    this._highlightDay(dayNum);
                });
            });
        }

        const body = this._buildRequestBody();
        if (this.costSummaryEl) {
            this.costSummaryEl.textContent =
                `总预算 ¥${structured.total_cost} / ${structured.days.length}天 · ${body.trip_params.num_people}人`;
        }
    }

    _renderDayCard(day) {
        const date = day.date || `第${day.day}天`;
        const attrHtml = (day.attractions || []).map(a =>
            `<li><strong>${this._esc(a.name)}</strong>${a.duration ? ` · ${a.duration}` : ''}${a.tip ? ` <em>💡${this._esc(a.tip)}</em>` : ''}</li>`
        ).join('');
        const mealHtml = (day.meals || []).map(m =>
            `<li>${this._esc(m.type)} · ${this._esc(m.name)}${m.price ? ` ¥${m.price}` : ''}</li>`
        ).join('');
        const hotel = day.hotel || {};
        const hotelHtml = hotel.name
            ? `<div class="card-section"><span class="card-section-icon">🏨</span><ul><li>${this._esc(hotel.name)}${hotel.price_per_night ? ` ¥${hotel.price_per_night}/晚` : ''}</li></ul></div>`
            : '';

        return `<div class="day-card expanded" data-day="${day.day}">
            <div class="day-card-header">
                <span class="day-card-title">📅 第 ${day.day} 天 · ${this._esc(date)}</span>
                <span class="day-card-cost">${day.estimated_cost ? `¥${day.estimated_cost}` : ''}</span>
                <span class="day-card-toggle">▼</span>
            </div>
            <div class="day-card-body">
                ${attrHtml ? `<div class="card-section"><span class="card-section-icon">🏛️</span><ul>${attrHtml}</ul></div>` : ''}
                ${mealHtml ? `<div class="card-section"><span class="card-section-icon">🍜</span><ul>${mealHtml}</ul></div>` : ''}
                ${hotelHtml}
            </div>
        </div>`;
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
            const { key } = await resp.json();
            if (!key) return;

            await new Promise((resolve, reject) => {
                const s = document.createElement('script');
                s.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}&plugin=AMap.Polyline`;
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
        this.markers = [];
        this.polylines = [];
    }

    _addMarkers(items, type) {
        if (!this.mapInstance || !window.AMap) return;
        const imgBlue = 'https://webapi.amap.com/theme/v1.3/markers/n/mark_b.png';
        const imgRed  = 'https://webapi.amap.com/theme/v1.3/markers/n/mark_r.png';
        const imgUrl  = type === 'hotel' ? imgRed : imgBlue;

        items.forEach(item => {
            if (!item.lng || !item.lat) return;
            const marker = new window.AMap.Marker({
                position: [item.lng, item.lat],
                title: item.name || '',
                map: this.mapInstance,
                icon: new window.AMap.Icon({
                    image: imgUrl,
                    size: new window.AMap.Size(19, 31),
                    imageSize: new window.AMap.Size(19, 31),
                }),
            });
            const label = type === 'hotel' ? `🏨 ${item.name}` : `🏛️ ${item.name}`;
            const info = new window.AMap.InfoWindow({
                content: `<div style="padding:6px 10px;font-size:13px">${label}</div>`,
                offset: new window.AMap.Pixel(0, -30),
            });
            marker.on('click', () => info.open(this.mapInstance, marker.getPosition()));
            this.markers.push(marker);
        });
    }

    _renderMapFromStructured(structured) {
        if (!this.mapInstance || !window.AMap || !structured?.days) return;

        const COLORS = ['#4A90E2', '#E2574A', '#50C878', '#FF8C00', '#9B59B6', '#1ABC9C', '#F39C12'];
        const allLngLat = [];

        structured.days.forEach((day, idx) => {
            const pts = [];
            (day.attractions || []).forEach(a => {
                if (a.lng && a.lat) { pts.push([a.lng, a.lat]); allLngLat.push([a.lng, a.lat]); }
            });
            if (day.hotel?.lng && day.hotel?.lat) {
                pts.push([day.hotel.lng, day.hotel.lat]);
                allLngLat.push([day.hotel.lng, day.hotel.lat]);
                this._addMarkers([day.hotel], 'hotel');
            }
            if (pts.length > 1) {
                const poly = new window.AMap.Polyline({
                    path: pts.map(p => new window.AMap.LngLat(p[0], p[1])),
                    strokeColor: COLORS[idx % COLORS.length],
                    strokeWeight: 3,
                    strokeOpacity: 0.9,
                    map: this.mapInstance,
                });
                this.polylines.push(poly);
            }
        });

        if (allLngLat.length) {
            const lngs = allLngLat.map(p => p[0]);
            const lats = allLngLat.map(p => p[1]);
            this.mapInstance.setBounds(new window.AMap.Bounds(
                new window.AMap.LngLat(Math.min(...lngs), Math.min(...lats)),
                new window.AMap.LngLat(Math.max(...lngs), Math.max(...lats)),
            ));
        }
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

    // Placeholder share methods (implemented in Task 10)
    _generateShareLink() {}
    _copyShareUrl() {}
    _closeShareModal() {}
}

document.addEventListener('DOMContentLoaded', () => { window.__app = new SuperBizAgentApp(); });
