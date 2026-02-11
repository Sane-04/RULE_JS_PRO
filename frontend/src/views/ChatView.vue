<template>
  <AppLayout>
    <section class="page">
      <header class="page-header">
        <div>
          <h2>智能问答</h2>
          <p>选择历史会话继续对话，支持滚动加载更多记录</p>
        </div>
        <div class="header-actions">
          <button class="btn ghost chat-mobile-toggle" type="button" @click="toggleSessionPanel">
            会话列表
          </button>
        </div>
      </header>

      <div class="page-body-scroll">
        <section class="chat-shell">
          <aside class="card chat-sidebar" :class="{ 'is-open': showSessionPanel }">
            <div class="chat-sidebar-head">
              <p class="chat-sidebar-title">历史会话</p>
              <button class="btn ghost" type="button" @click="startNewSession" :disabled="sending">新会话</button>
            </div>
            <div ref="sessionListRef" class="chat-session-list" @scroll.passive="handleSessionScroll">
              <button
                v-for="session in sessions"
                :key="session.session_id"
                class="chat-session-item"
                :class="{ 'is-active': session.session_id === activeSessionId }"
                type="button"
                @click="openSession(session.session_id)"
              >
                <span class="chat-session-preview">{{ session.preview || "空会话" }}</span>
                <span class="chat-session-time">{{ formatSessionTime(session.last_active_at) }}</span>
              </button>
              <p v-if="sessionsLoading && !sessions.length" class="chat-side-tip">加载会话中...</p>
              <p v-else-if="!sessionsLoading && !sessions.length" class="chat-side-tip">暂无历史会话</p>
              <p v-if="sessionsLoadingMore" class="chat-side-tip">加载更多会话...</p>
              <p v-else-if="!sessionsHasMore && sessions.length" class="chat-side-tip">没有更多会话了</p>
              <p v-if="sessionError" class="error-text chat-side-error">{{ sessionError }}</p>
            </div>
          </aside>

          <section class="card chat-main">
            <div class="chat-main-head">
              <span class="chat-session">会话: {{ activeSessionId || "未选择" }}</span>
              <button class="btn ghost" type="button" @click="startNewSession" :disabled="sending">新会话</button>
            </div>

            <div v-if="!activeSessionId && !timeline.length" class="chat-empty">
              <p>请选择左侧会话，或点击“新会话”开始对话。</p>
            </div>

            <div
              v-else
              ref="messageListRef"
              class="chat-message-list"
              @scroll.passive="handleMessageScroll"
            >
              <p v-if="messagesLoadingMore" class="chat-load-tip">加载更早消息...</p>
              <p v-if="messagesLoading && !timeline.length" class="chat-load-tip">加载消息中...</p>
              <div
                v-for="item in timeline"
                :key="item.id ? `msg-${item.id}` : `tmp-${item.role}-${item.content}`"
                class="chat-msg-row"
                :class="item.role === 'user' ? 'is-user' : 'is-assistant'"
              >
                <div class="chat-msg-bubble">{{ item.content }}</div>
              </div>
              <p v-if="activeSessionId && !timeline.length && !messagesLoading" class="chat-load-tip">该会话暂无消息</p>
              <p v-if="!messagesHasOlder && timeline.length" class="chat-load-tip">已显示最近消息</p>
            </div>

            <section class="chat-composer">
              <label class="chat-label" for="chat-message">输入问题</label>
              <textarea
                id="chat-message"
                v-model="message"
                class="chat-textarea"
                placeholder="输入问题后发送，未选会话将自动创建新会话"
              />
              <div class="chat-actions">
                <button class="btn primary" type="button" @click="submitMessage" :disabled="sending || !message.trim()">
                  {{ sending ? "发送中..." : "发送" }}
                </button>
              </div>
              <p v-if="error" class="error-text">{{ error }}</p>
            </section>
          </section>
        </section>
      </div>
    </section>
  </AppLayout>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from "vue";

import AppLayout from "../layouts/AppLayout.vue";
import {
  getChatSessionMessages,
  getChatSessions,
  postChat,
  type ChatSessionItem,
  type ChatSessionMessageItem,
} from "../api/chat";

type TimelineMessage = {
  id?: number;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
};

const SESSION_PAGE_SIZE = 20;
const MESSAGE_PAGE_SIZE = 20;

const showSessionPanel = ref(false);
const sessionListRef = ref<HTMLElement | null>(null);
const messageListRef = ref<HTMLElement | null>(null);

const sessions = ref<ChatSessionItem[]>([]);
const sessionsLoading = ref(false);
const sessionsLoadingMore = ref(false);
const sessionsHasMore = ref(true);
const sessionOffset = ref(0);
const sessionError = ref("");

const activeSessionId = ref("");
const timeline = ref<TimelineMessage[]>([]);
const messagesLoading = ref(false);
const messagesLoadingMore = ref(false);
const messagesHasOlder = ref(false);
const messageStartOffset = ref(0);

const message = ref("");
const sending = ref(false);
const error = ref("");

const formatSessionTime = (value: string): string => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  return `${month}-${day} ${hour}:${minute}`;
};

const scrollToMessageBottom = () => {
  const el = messageListRef.value;
  if (!el) return;
  el.scrollTop = el.scrollHeight;
};

const loadMoreSessions = async () => {
  if (!sessionsHasMore.value) return;
  if (sessionsLoading.value || sessionsLoadingMore.value) return;
  const isFirstPage = sessionOffset.value === 0;
  if (isFirstPage) {
    sessionsLoading.value = true;
  } else {
    sessionsLoadingMore.value = true;
  }
  try {
    const resp = await getChatSessions({
      offset: sessionOffset.value,
      limit: SESSION_PAGE_SIZE,
    });
    const existing = new Set(sessions.value.map((item) => item.session_id));
    const incoming: ChatSessionItem[] = [];
    for (const item of resp.data) {
      if (!existing.has(item.session_id)) {
        incoming.push(item);
      }
    }
    sessions.value = [...sessions.value, ...incoming];
    sessionOffset.value += resp.data.length;
    sessionsHasMore.value = sessionOffset.value < resp.meta.total;
  } catch (err: any) {
    sessionError.value = err?.response?.data?.message ?? "加载会话失败";
  } finally {
    sessionsLoading.value = false;
    sessionsLoadingMore.value = false;
  }
};

const refreshSessions = async () => {
  sessions.value = [];
  sessionsHasMore.value = true;
  sessionOffset.value = 0;
  sessionError.value = "";
  await loadMoreSessions();
};

const mapMessages = (rows: ChatSessionMessageItem[]): TimelineMessage[] => {
  return rows.map((item) => ({
    id: item.id,
    role: item.role === "assistant" ? "assistant" : "user",
    content: item.content,
    created_at: item.created_at,
  }));
};

const loadSessionMessages = async (sessionId: string) => {
  messagesLoading.value = true;
  messagesLoadingMore.value = false;
  messagesHasOlder.value = false;
  messageStartOffset.value = 0;
  timeline.value = [];
  error.value = "";
  try {
    const probe = await getChatSessionMessages(sessionId, { offset: 0, limit: 1 });
    const total = probe.meta.total;
    if (total <= 0) {
      messagesHasOlder.value = false;
      return;
    }
    const startOffset = Math.max(total - MESSAGE_PAGE_SIZE, 0);
    const page = await getChatSessionMessages(sessionId, {
      offset: startOffset,
      limit: MESSAGE_PAGE_SIZE,
    });
    timeline.value = mapMessages(page.data);
    messageStartOffset.value = startOffset;
    messagesHasOlder.value = startOffset > 0;
    await nextTick();
    scrollToMessageBottom();
  } catch (err: any) {
    error.value = err?.response?.data?.message ?? "加载会话消息失败";
  } finally {
    messagesLoading.value = false;
  }
};

const loadOlderMessages = async () => {
  if (!activeSessionId.value) return;
  if (!messagesHasOlder.value || messagesLoading.value || messagesLoadingMore.value) return;
  const nextOffset = Math.max(messageStartOffset.value - MESSAGE_PAGE_SIZE, 0);
  const nextLimit = messageStartOffset.value - nextOffset;
  if (nextLimit <= 0) {
    messagesHasOlder.value = false;
    return;
  }
  const container = messageListRef.value;
  const prevHeight = container?.scrollHeight ?? 0;
  const prevTop = container?.scrollTop ?? 0;
  messagesLoadingMore.value = true;
  try {
    const resp = await getChatSessionMessages(activeSessionId.value, {
      offset: nextOffset,
      limit: nextLimit,
    });
    const olderRows = mapMessages(resp.data);
    timeline.value = [...olderRows, ...timeline.value];
    messageStartOffset.value = nextOffset;
    messagesHasOlder.value = nextOffset > 0;
    await nextTick();
    if (container) {
      container.scrollTop = container.scrollHeight - prevHeight + prevTop;
    }
  } catch (err: any) {
    error.value = err?.response?.data?.message ?? "加载更早消息失败";
  } finally {
    messagesLoadingMore.value = false;
  }
};

const openSession = async (sessionId: string) => {
  if (!sessionId) return;
  activeSessionId.value = sessionId;
  await loadSessionMessages(sessionId);
  if (window.innerWidth <= 960) {
    showSessionPanel.value = false;
  }
};

const startNewSession = () => {
  activeSessionId.value = "";
  timeline.value = [];
  message.value = "";
  error.value = "";
  messagesLoading.value = false;
  messagesLoadingMore.value = false;
  messagesHasOlder.value = false;
  messageStartOffset.value = 0;
  if (window.innerWidth <= 960) {
    showSessionPanel.value = false;
  }
};

const submitMessage = async () => {
  const text = message.value.trim();
  if (!text) return;
  sending.value = true;
  error.value = "";
  try {
    const resp = await postChat({
      session_id: activeSessionId.value || undefined,
      message: text,
    });
    activeSessionId.value = resp.data.session_id;
    timeline.value.push({ role: "user", content: text });
    timeline.value.push({ role: "assistant", content: resp.data.summary });
    message.value = "";
    await refreshSessions();
    await nextTick();
    scrollToMessageBottom();
  } catch (err: any) {
    error.value = err?.response?.data?.message ?? "请求失败";
  } finally {
    sending.value = false;
  }
};

const handleSessionScroll = () => {
  const el = sessionListRef.value;
  if (!el || sessionsLoading.value || sessionsLoadingMore.value || !sessionsHasMore.value) return;
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 40) {
    void loadMoreSessions();
  }
};

const handleMessageScroll = () => {
  const el = messageListRef.value;
  if (!el || messagesLoading.value || messagesLoadingMore.value || !messagesHasOlder.value) return;
  if (el.scrollTop <= 40) {
    void loadOlderMessages();
  }
};

const toggleSessionPanel = () => {
  showSessionPanel.value = !showSessionPanel.value;
};

onMounted(() => {
  void refreshSessions();
});
</script>
