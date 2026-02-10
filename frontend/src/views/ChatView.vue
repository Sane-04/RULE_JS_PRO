<template>
  <AppLayout>
    <section class="page">
      <header class="page-header">
        <div>
          <h2>智能问答</h2>
          <p>统一工作流（意图识别 + 任务解析）</p>
        </div>
        <div class="header-actions">
          <span class="chat-session">会话: {{ sessionId || "未创建" }}</span>
          <button class="btn ghost" type="button" @click="resetSession" :disabled="loading">新会话</button>
        </div>
      </header>

      <section class="card chat-input-card">
        <label class="chat-label" for="chat-message">输入问题</label>
        <textarea
          id="chat-message"
          v-model="message"
          class="chat-textarea"
          placeholder="例如：查询22级软件工程男生人数，按班级从高到低"
        />
        <div class="chat-actions">
          <button class="btn primary" type="button" @click="submitMessage" :disabled="loading || !message.trim()">
            {{ loading ? "执行中..." : "执行工作流" }}
          </button>
        </div>
        <p v-if="error" class="error-text">{{ error }}</p>
      </section>

      <section class="card chat-result-card" v-if="result">
        <div class="chat-kv-grid">
          <div class="chat-kv">
            <span class="chat-kv-label">intent</span>
            <span class="chat-kv-value">{{ result.intent }}</span>
          </div>
          <div class="chat-kv">
            <span class="chat-kv-label">is_followup</span>
            <span class="chat-kv-value">{{ result.is_followup ? "true" : "false" }}</span>
          </div>
          <div class="chat-kv">
            <span class="chat-kv-label">skipped</span>
            <span class="chat-kv-value">{{ result.skipped ? "true" : "false" }}</span>
          </div>
          <div class="chat-kv">
            <span class="chat-kv-label">reason</span>
            <span class="chat-kv-value">{{ result.reason || "-" }}</span>
          </div>
        </div>

        <div class="chat-block">
          <p class="chat-block-title">merged_query</p>
          <p class="chat-block-content">{{ result.merged_query }}</p>
        </div>
        <div class="chat-block">
          <p class="chat-block-title">rewritten_query</p>
          <p class="chat-block-content">{{ result.rewritten_query }}</p>
        </div>
        <div class="chat-block">
          <p class="chat-block-title">task</p>
          <pre class="chat-json">{{ formatJson(result.task) }}</pre>
        </div>
        <div class="chat-block">
          <p class="chat-block-title">sql_result</p>
          <pre class="chat-json">{{ formatJson(result.sql_result) }}</pre>
        </div>
      </section>

      <section class="card chat-history-card" v-if="timeline.length">
        <div class="table-meta">
          <div>
            <p class="table-title">本地对话记录</p>
            <p class="table-sub">仅用于页面展示，后端上下文统一从数据库读取</p>
          </div>
        </div>
        <ul class="chat-history-list">
          <li v-for="(item, index) in timeline" :key="`chat-row-${index}`" class="chat-history-item">
            <span class="chat-role" :class="item.role === 'user' ? 'is-user' : 'is-assistant'">
              {{ item.role }}
            </span>
            <span class="chat-content">{{ item.content }}</span>
          </li>
        </ul>
      </section>
    </section>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref } from "vue";

import AppLayout from "../layouts/AppLayout.vue";
import { postChat, type ChatData } from "../api/chat";

type TimelineMessage = {
  role: "user" | "assistant";
  content: string;
};

const loading = ref(false);
const error = ref("");
const message = ref("");
const sessionId = ref("");
const result = ref<ChatData | null>(null);
const timeline = ref<TimelineMessage[]>([]);

const submitMessage = async () => {
  const text = message.value.trim();
  if (!text) return;
  loading.value = true;
  error.value = "";
  try {
    const resp = await postChat({
      session_id: sessionId.value || undefined,
      message: text,
    });
    result.value = resp.data;
    sessionId.value = resp.data.session_id;
    timeline.value.push({ role: "user", content: text });
    timeline.value.push({ role: "assistant", content: resp.data.rewritten_query });
    message.value = "";
  } catch (err: any) {
    error.value = err?.response?.data?.message ?? "请求失败";
  } finally {
    loading.value = false;
  }
};

const resetSession = () => {
  sessionId.value = "";
  message.value = "";
  result.value = null;
  error.value = "";
  timeline.value = [];
};

const formatJson = (value: unknown): string => JSON.stringify(value, null, 2);
</script>
