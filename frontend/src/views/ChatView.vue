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
import { postChat } from "../api/chat";

type TimelineMessage = {
  role: "user" | "assistant";
  content: string;
};

const loading = ref(false);
const error = ref("");
const message = ref("");
const sessionId = ref("");
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
    sessionId.value = resp.data.session_id;
    timeline.value.push({ role: "user", content: text });
    timeline.value.push({ role: "assistant", content: resp.data.summary });
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
  error.value = "";
  timeline.value = [];
};
</script>
