<template>
  <AppLayout>
    <section class="page">
      <header class="page-header">
        <div>
          <h2>驾驶舱总览</h2>
          <p>学期与组织维度联动的关键指标与风险视图</p>
        </div>
        <div class="header-actions">
          <button class="btn ghost" type="button" @click="fetchOverview" :disabled="loading">
            {{ loading ? "加载中..." : "刷新" }}
          </button>
          <button class="btn primary" type="button" @click="exportRisk" :disabled="loading">
            导出风险清单
          </button>
        </div>
      </header>

      <div class="page-body-scroll">
        <section class="card filter-panel">
          <div class="filter-grid">
            <div class="filter-field">
              <label>学期</label>
              <select v-model="filters.term">
                <option value="">全部</option>
                <option v-for="term in filterOptions.terms" :key="term" :value="term">
                  {{ term }}
                </option>
              </select>
            </div>
            <div class="filter-field">
              <label>学院</label>
              <select v-model="filters.college_id">
                <option value="">全部</option>
                <option v-for="item in filterOptions.colleges" :key="item.value" :value="String(item.value)">
                  {{ item.label }}
                </option>
              </select>
            </div>
            <div class="filter-field">
              <label>专业</label>
              <select v-model="filters.major_id">
                <option value="">全部</option>
                <option v-for="item in filteredMajors" :key="item.value" :value="String(item.value)">
                  {{ item.label }}
                </option>
              </select>
            </div>
            <div class="filter-field">
              <label>年级</label>
              <select v-model="filters.grade_year">
                <option value="">全部</option>
                <option v-for="item in filterOptions.grades" :key="item" :value="String(item)">
                  {{ item }}
                </option>
              </select>
            </div>
            <div class="filter-actions">
              <button class="btn ghost" type="button" @click="applyFilters" :disabled="loading">
                应用筛选
              </button>
              <button class="btn ghost" type="button" @click="resetFilters" :disabled="loading">
                重置
              </button>
            </div>
          </div>
        </section>

        <section class="cockpit-grid">
          <div
            class="card metric-card"
            v-for="card in cards"
            :key="card.code"
            :style="{ '--metric-accent': metricAccent(card.code) }"
          >
            <div class="metric-info">
              <p class="metric-name">{{ card.name }}</p>
              <p class="metric-value">{{ formatValue(card) }}</p>
              <span class="metric-tag">{{ card.code }}</span>
            </div>
            <div
              class="metric-icon"
              :style="{
                background: metricSoft(card.code),
                color: metricAccent(card.code),
              }"
            >
              {{ metricIcon(card.code) }}
            </div>
          </div>
        </section>

        <section class="cockpit-row">
          <div class="card trend-card">
            <div class="card-head">
              <div>
                <p class="table-title">趋势对比</p>
                <p class="table-sub">近 6 个月出勤率</p>
              </div>
            </div>
            <div v-if="loading" class="table-state">正在加载趋势...</div>
            <div v-else class="trend-chart">
              <div class="trend-plot">
                <div class="trend-ylabels">
                  <span>100%</span>
                  <span>90%</span>
                  <span>80%</span>
                  <span>70%</span>
                  <span>60%</span>
                </div>
                <svg viewBox="0 0 320 140" preserveAspectRatio="none" role="img" aria-label="trend">
                  <g class="trend-yaxis">
                    <line x1="10" y1="30" x2="310" y2="30" stroke="#e5e7eb" stroke-width="1" />
                    <line x1="10" y1="52.5" x2="310" y2="52.5" stroke="#e5e7eb" stroke-width="1" />
                    <line x1="10" y1="75" x2="310" y2="75" stroke="#e5e7eb" stroke-width="1" />
                    <line x1="10" y1="97.5" x2="310" y2="97.5" stroke="#e5e7eb" stroke-width="1" />
                    <line x1="10" y1="120" x2="310" y2="120" stroke="#e5e7eb" stroke-width="1" />
                  </g>
                  <polyline :points="trendLine(attendance)" fill="none" stroke="#1f7a8c" stroke-width="3" />
                </svg>
              </div>
              <div class="trend-legend">
                <span><i class="legend-dot teal"></i>出勤率</span>
              </div>
              <div class="trend-axis" :style="{ gridTemplateColumns: `repeat(${Math.max(trends.length, 1)}, 1fr)` }">
                <span v-for="item in trends" :key="item.date">{{ item.date.slice(5) }}</span>
              </div>
            </div>
          </div>

          <div class="card dist-card">
            <div class="card-head">
              <div>
                <p class="table-title">结构分布</p>
                <p class="table-sub">学院规模与成绩段分布</p>
              </div>
              <div class="tab-group">
                <button
                  class="tab-btn"
                  :class="{ active: distTab === 'college' }"
                  type="button"
                  @click="distTab = 'college'"
                >
                  College Scale
                </button>
                <button
                  class="tab-btn"
                  :class="{ active: distTab === 'score' }"
                  type="button"
                  @click="distTab = 'score'"
                >
                  Grade Dist.
                </button>
              </div>
            </div>
            <div v-if="distTab === 'college'" class="bar-chart">
              <div v-if="distributions.college_students.length === 0" class="table-state">No data</div>
              <div v-else class="bar-list">
                <div v-for="item in distributions.college_students" :key="item.name" class="bar-row">
                  <span class="bar-label" :title="item.name">{{ item.name }}</span>
                  <div class="bar-track">
                    <span class="bar-fill" :style="{ width: calcBar(item.value, collegeMax) }"></span>
                  </div>
                  <span class="bar-value">{{ formatNumber(item.value) }}</span>
                </div>
              </div>
            </div>
            <div v-else class="donut-wrap">
              <div v-if="scoreTotal === 0" class="table-state">No data</div>
              <div v-else class="donut-layout">
                <svg class="donut-chart" viewBox="0 0 120 120" role="img" aria-label="score">
                  <g transform="rotate(-90 60 60)">
                    <circle
                      v-for="segment in scoreSegments"
                      :key="segment.name"
                      cx="60"
                      cy="60"
                      r="42"
                      fill="none"
                      :stroke="segment.color"
                      stroke-width="12"
                      :stroke-dasharray="segment.dasharray"
                      :stroke-dashoffset="segment.dashoffset"
                      stroke-linecap="round"
                    />
                  </g>
                </svg>
                <div class="donut-legend">
                  <div v-for="segment in scoreSegments" :key="segment.name" class="legend-item">
                    <span class="legend-dot" :style="{ background: segment.color }"></span>
                    <span class="legend-name">{{ segment.name }}</span>
                    <span class="legend-value">{{ formatNumber(segment.value) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="cockpit-row">
          <div class="card rank-card">
            <div class="card-head">
              <div>
                <p class="table-title">风险榜单</p>
                <p class="table-sub">挂科率与缺勤率 Top</p>
              </div>
              <button class="btn ghost" type="button" @click="goToData('course')">查看课程</button>
            </div>
            <div class="rank-grid">
              <div>
                <p class="rank-title">课程挂科率</p>
                <ol class="rank-list">
                  <li v-for="(item, index) in sortedCourseFailRate" :key="item.name" class="rank-item">
                    <span class="rank-badge" :class="rankClass(index)" :style="rankBadgeStyle(index)">{{ index + 1 }}</span>
                    <div class="rank-body">
                      <span class="rank-name">{{ item.name }}</span>
                      <div class="rank-progress">
                        <span class="rank-value">{{ toPercent(item.value) }}</span>
                        <div class="mini-progress">
                          <span class="mini-bar" :class="riskBarClass(item.value)" :style="{ width: toPercent(item.value) }"></span>
                        </div>
                      </div>
                    </div>
                  </li>
                </ol>
              </div>
              <div>
                <p class="rank-title">班级缺勤率</p>
                <ol class="rank-list">
                  <li v-for="(item, index) in sortedClassAbsentRate" :key="item.name" class="rank-item">
                    <span class="rank-badge" :class="rankClass(index)" :style="rankBadgeStyle(index)">{{ index + 1 }}</span>
                    <div class="rank-body">
                      <span class="rank-name">{{ item.name }}</span>
                      <div class="rank-progress">
                        <span class="rank-value">{{ toPercent(item.value) }}</span>
                        <div class="mini-progress">
                          <span class="mini-bar" :class="riskBarClass(item.value)" :style="{ width: toPercent(item.value) }"></span>
                        </div>
                      </div>
                    </div>
                  </li>
                </ol>
              </div>
            </div>
          </div>

          <div class="card alert-card">
            <div class="card-head">
              <div>
                <p class="table-title">高风险学生</p>
                <p class="table-sub">挂科累计提醒</p>
              </div>
              <button class="btn ghost" type="button" @click="goToData('student')">查看学生</button>
            </div>
            <div v-if="loading" class="table-state">正在加载风险清单...</div>
            <div v-else-if="risks.length === 0" class="table-state">暂无风险</div>
            <ul v-else class="alert-list">
              <li v-for="item in risks" :key="item.title" class="alert-item">
                <span class="alert-level">{{ item.level }}</span>
                <div>
                  <p>{{ item.title }}</p>
                  <small>{{ item.message }}</small>
                </div>
              </li>
            </ul>
          </div>
        </section>

        <p v-if="error" class="error-text">{{ error }}</p>
      </div>
    </section>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";

import api from "../api/client";
import AppLayout from "../layouts/AppLayout.vue";

type OptionItem = { value: number | string; label: string };
type FilterOptions = { terms: string[]; colleges: OptionItem[]; majors: OptionItem[]; grades: number[] };
type CardItem = { code: string; name: string; value: number; unit?: string | null };
type TrendItem = { date: string; attendance_rate: number };
type DistributionItem = { name: string; value: number };
type RankingItem = { name: string; value: number };
type RiskItem = { level: string; title: string; message: string };
type MajorItem = { id: number; major_name: string; college_id: number };

const router = useRouter();
const cards = ref<CardItem[]>([]);
const trends = ref<TrendItem[]>([]);
const risks = ref<RiskItem[]>([]);
const distributions = ref<{ college_students: DistributionItem[]; score_band: DistributionItem[] }>({
  college_students: [],
  score_band: [],
});
const rankings = ref<{ course_fail_rate: RankingItem[]; class_absent_rate: RankingItem[] }>({
  course_fail_rate: [],
  class_absent_rate: [],
});
const sortedCourseFailRate = computed(() => {
  return [...rankings.value.course_fail_rate].sort((a, b) => b.value - a.value);
});
const sortedClassAbsentRate = computed(() => {
  return [...rankings.value.class_absent_rate].sort((a, b) => b.value - a.value);
});
const filterOptions = ref<FilterOptions>({ terms: [], colleges: [], majors: [], grades: [] });
const allMajors = ref<MajorItem[]>([]);
const loading = ref(false);
const error = ref("");

const filters = reactive({
  term: "",
  college_id: "",
  major_id: "",
  grade_year: "",
});
const distTab = ref<"college" | "score">("college");

const attendance = computed(() => trends.value.map((item) => item.attendance_rate));
const filteredMajors = computed(() => {
  if (!filters.college_id) {
    return filterOptions.value.majors;
  }
  const collegeId = Number(filters.college_id);
  return allMajors.value
    .filter((item) => item.college_id === collegeId)
    .map((item) => ({ value: item.id, label: item.major_name }));
});

const collegeMax = computed(() => Math.max(...distributions.value.college_students.map((i) => i.value), 1));
const scoreColor = (name: string) => {
  const normalized = (name || "").toLowerCase();
  if (normalized.includes("90") || normalized.includes("优秀")) {
    return "#22c55e";
  }
  if (normalized.includes("80") || normalized.includes("良好")) {
    return "#3b82f6";
  }
  if (normalized.includes("70") || normalized.includes("中等")) {
    return "#6366f1";
  }
  if (normalized.includes("60") || normalized.includes("及格")) {
    return "#f59e0b";
  }
  if (normalized.includes("不及格") || normalized.includes("fail") || normalized.includes("0")) {
    return "#ef4444";
  }
  return "#a855f7";
};

const scoreTotal = computed(() => distributions.value.score_band.reduce((sum, item) => sum + item.value, 0));
const scoreSegments = computed(() => {
  const total = scoreTotal.value;
  if (!total) {
    return [];
  }
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return distributions.value.score_band.map((item) => {
    const size = (item.value / total) * circumference;
    const segment = {
      name: item.name,
      value: item.value,
      color: scoreColor(item.name),
      dasharray: `${size} ${circumference - size}`,
      dashoffset: -offset,
    };
    offset += size;
    return segment;
  });
});

const formatNumber = (value: number) => {
  if (Number.isNaN(value)) {
    return "-";
  }
  return new Intl.NumberFormat("zh-CN").format(value);
};

const toPercent = (value: number) => `${(value * 100).toFixed(1)}%`;

const formatValue = (card: CardItem) => {
  if (card.unit === "ratio") {
    return toPercent(card.value);
  }
  return formatNumber(card.value);
};

const calcBar = (value: number, max: number) => {
  if (!max) {
    return "0%";
  }
  return `${Math.min(100, (value / max) * 100)}%`;
};

const trendLine = (values: number[]) => {
  if (!values.length) {
    return "";
  }
  const max = 1.0;
  const min = 0.6;
  const range = max - min || 1;
  return values
    .map((value, index) => {
      const x = (index / (values.length - 1 || 1)) * 300 + 10;
      const y = 120 - ((value - min) / range) * 90;
      return `${x},${y}`;
    })
    .join(" ");
};

const metricIcon = (code: string) => {
  const normalized = code?.toLowerCase() || "";
  if (normalized.includes("student") || normalized.includes("stu")) {
    return "S";
  }
  if (normalized.includes("teacher") || normalized.includes("teach")) {
    return "T";
  }
  if (normalized.includes("course") || normalized.includes("class")) {
    return "C";
  }
  if (normalized.includes("risk") || normalized.includes("alert")) {
    return "R";
  }
  return "K";
};

const metricAccent = (code: string) => {
  const normalized = code?.toLowerCase() || "";
  if (normalized.includes("student") || normalized.includes("stu")) {
    return "#2563eb";
  }
  if (normalized.includes("teacher") || normalized.includes("teach")) {
    return "#0f766e";
  }
  if (normalized.includes("course") || normalized.includes("class")) {
    return "#7c3aed";
  }
  if (normalized.includes("risk") || normalized.includes("alert")) {
    return "#dc2626";
  }
  return "#1d4ed8";
};

const metricSoft = (code: string) => {
  const normalized = code?.toLowerCase() || "";
  if (normalized.includes("student") || normalized.includes("stu")) {
    return "#dbeafe";
  }
  if (normalized.includes("teacher") || normalized.includes("teach")) {
    return "#ccfbf1";
  }
  if (normalized.includes("course") || normalized.includes("class")) {
    return "#ede9fe";
  }
  if (normalized.includes("risk") || normalized.includes("alert")) {
    return "#fee2e2";
  }
  return "#dbeafe";
};

const rankClass = (index: number) => {
  if (index === 0) return "gold";
  if (index === 1) return "silver";
  if (index === 2) return "bronze";
  return "normal";
};

const rankBadgeStyle = (index: number) => {
  if (index === 0) {
    return { backgroundColor: "#dc2626", color: "#fee2e2" };
  }
  if (index === 1) {
    return { backgroundColor: "#ef4444", color: "#fee2e2" };
  }
  if (index === 2) {
    return { backgroundColor: "#f87171", color: "#7f1d1d" };
  }
  return { backgroundColor: "#fee2e2", color: "#991b1b" };
};

const riskBarClass = (value: number) => {
  return value > 0.2 ? "high" : "medium";
};

const buildParams = () => {
  const params: Record<string, any> = {};
  if (filters.term) {
    params.term = filters.term;
  }
  if (filters.college_id) {
    params.college_id = Number(filters.college_id);
  }
  if (filters.major_id) {
    params.major_id = Number(filters.major_id);
  }
  if (filters.grade_year) {
    params.grade_year = Number(filters.grade_year);
  }
  return params;
};

const fetchOverview = async () => {
  loading.value = true;
  error.value = "";
  try {
    const res = await api.get("/cockpit/overview", { params: buildParams() });
    const data = res.data.data || {};
    cards.value = data.cards || [];
    trends.value = data.trends || [];
    risks.value = data.risks || [];
    distributions.value = data.distributions || { college_students: [], score_band: [] };
    rankings.value = data.rankings || { course_fail_rate: [], class_absent_rate: [] };
    filterOptions.value = data.filters || { terms: [], colleges: [], majors: [], grades: [] };
  } catch (err: any) {
    error.value = err?.response?.data?.message || "驾驶舱加载失败，请稍后重试";
  } finally {
    loading.value = false;
  }
};

const fetchMajors = async () => {
  const items: MajorItem[] = [];
  let offset = 0;
  const limit = 200;
  try {
    while (true) {
      const res = await api.get("/data/major/list", { params: { offset, limit } });
      const data = res.data.data || [];
      items.push(...data);
      if (data.length < limit) {
        break;
      }
      offset += limit;
    }
    allMajors.value = items;
  } catch {
    allMajors.value = [];
  }
};

const applyFilters = () => {
  fetchOverview();
};

const resetFilters = () => {
  filters.term = "";
  filters.college_id = "";
  filters.major_id = "";
  filters.grade_year = "";
  fetchOverview();
};

watch(
  () => filters.college_id,
  () => {
    if (filters.major_id) {
      const valid = filteredMajors.value.some((item) => String(item.value) === String(filters.major_id));
      if (!valid) {
        filters.major_id = "";
      }
    }
  }
);

const goToData = (table: string) => {
  const query: Record<string, any> = { table };
  if (filters.college_id) {
    query.college_id = filters.college_id;
  }
  if (filters.major_id) {
    query.major_id = filters.major_id;
  }
  if (filters.grade_year) {
    query.enroll_year = filters.grade_year;
  }
  router.push({ name: "data", query });
};

const exportRisk = async () => {
  try {
    const res = await api.get("/cockpit/risk/export", {
      params: buildParams(),
      responseType: "blob",
    });
    const url = window.URL.createObjectURL(res.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = "risk_list.csv";
    link.click();
    window.URL.revokeObjectURL(url);
  } catch (err: any) {
    error.value = err?.response?.data?.message || "导出失败";
  }
};

onMounted(async () => {
  await fetchMajors();
  await fetchOverview();
});
</script>
