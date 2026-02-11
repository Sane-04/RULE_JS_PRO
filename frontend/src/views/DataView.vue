<template>
  <AppLayout>
    <section class="page">
      <header class="page-header">
        <div>
          <h2>数据管理</h2>
          <p>核心表数据浏览、筛选与维护</p>
        </div>
        <div class="header-actions">
          <button class="btn ghost" type="button" @click="fetchData" :disabled="loading">
            {{ loading ? "加载中..." : "刷新" }}
          </button>
          <button class="btn primary" type="button" @click="openCreate">新增</button>
        </div>
      </header>

      <div class="page-body-scroll">
        <section class="card filter-card">
        <div class="filter-row">
          <div class="filter-group">
            <span class="filter-label">数据表</span>
            <div class="table-switcher">
              <button
                v-for="option in tableOptions"
                :key="option.key"
                class="switcher-btn"
                :class="{ active: option.key === tableKey }"
                type="button"
                @click="changeTable(option.key)"
              >
                {{ option.label }}
              </button>
            </div>
          </div>
        </div>
        <div class="filter-row">
          <div class="filter-group">
            <span class="filter-label">关键词</span>
            <input v-model="keyword" class="filter-input" placeholder="支持模糊匹配" />
          </div>
          <div class="filter-actions">
            <button class="btn ghost" type="button" @click="applyFilters" :disabled="loading">
              搜索
            </button>
            <button class="btn ghost" type="button" @click="resetFilters" :disabled="loading">
              重置
            </button>
          </div>
        </div>
        <div class="filter-list">
          <div v-for="(item, index) in filters" :key="`filter-${index}`" class="filter-item">
            <select v-model="item.key" class="filter-select">
              <option value="">字段</option>
              <option v-for="field in currentFields" :key="field.key" :value="field.key">
                {{ field.label }}
              </option>
            </select>
            <input v-model="item.value" class="filter-input" placeholder="填写值" />
            <button class="btn ghost filter-remove" type="button" @click="removeFilter(index)">
              移除
            </button>
          </div>
          <button class="btn ghost" type="button" @click="addFilter">添加条件</button>
        </div>
        </section>

        <section class="card">
        <div class="table-meta">
          <div>
            <p class="table-title">{{ currentTable.label }}列表</p>
            <p class="table-sub">支持筛选、分页与增删改查（软删除）</p>
          </div>
          <span class="meta-count">共 {{ meta.total }} 条</span>
        </div>

        <div v-if="loading" class="table-state">正在加载数据...</div>
        <div v-else-if="error" class="table-state error-text">{{ error }}</div>
        <div v-else-if="rows.length === 0" class="table-state">暂无数据</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th v-for="col in currentTable.columns" :key="col.key">{{ col.label }}</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in rows" :key="item.id">
              <td v-for="col in currentTable.columns" :key="col.key">
                <span
                  v-if="col.key === 'status' && item[col.key]"
                  class="status-badge"
                  :class="statusClass(item[col.key])"
                >
                  {{ item[col.key] }}
                </span>
                <span v-else>
                  {{ item[col.key] ?? "-" }}
                </span>
              </td>
              <td>
                <div class="table-actions">
                  <button class="btn action edit" type="button" @click="openEdit(item)">编辑</button>
                  <button
                    v-if="tableKey === 'student'"
                    class="btn action view"
                    type="button"
                    @click="openScores(item)"
                  >
                    成绩
                  </button>
                  <button class="btn action delete" type="button" @click="removeItem(item)">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>

        <PaginationBar
          :page="page"
          :page-size="pageSize"
          :total="meta.total"
          @page-change="handlePageChange"
          @page-size-change="handlePageSizeChange"
        />
        </section>
      </div>
    </section>

    <DataFormModal
      :visible="modalVisible"
      :title="modalTitle"
      :fields="currentFields"
      :model-value="formState"
      :loading="formLoading"
      :error="formError"
      @update:modelValue="updateFormState"
      @submit="submitForm"
      @close="closeModal"
    />

    <ScoreListModal
      :visible="scoreModalVisible"
      :title="`成绩明细 - ${scoreStudentName}`"
      :rows="scoreRows"
      :loading="scoreLoading"
      :error="scoreError"
      @close="closeScoreModal"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import api from "../api/client";
import DataFormModal from "../components/DataFormModal.vue";
import PaginationBar from "../components/PaginationBar.vue";
import ScoreListModal from "../components/ScoreListModal.vue";
import AppLayout from "../layouts/AppLayout.vue";

type ColumnDef = {
  key: string;
  label: string;
};

type FieldDef = {
  key: string;
  label: string;
  type: "text" | "number" | "date" | "textarea";
  required?: boolean;
  placeholder?: string;
  readonly?: boolean;
};

type TableOption = {
  key: string;
  label: string;
  columns: ColumnDef[];
  fields: FieldDef[];
};

type MetaInfo = {
  offset: number;
  limit: number;
  total: number;
};

type FilterItem = {
  key: string;
  value: string;
};

type ScoreRow = {
  id: number;
  course_name?: string;
  term?: string;
  score_value?: number | null;
  score_level?: string | null;
};

type NameMaps = {
  colleges: Record<number, string>;
  majors: Record<number, string>;
  classes: Record<number, string>;
  teachers: Record<number, string>;
};

const route = useRoute();

const tableOptions: TableOption[] = [
  {
    key: "student",
    label: "学生",
    columns: [
      { key: "student_no", label: "学号" },
      { key: "real_name", label: "姓名" },
      { key: "gender", label: "性别" },
      { key: "enroll_year", label: "入学年份" },
      { key: "class_name", label: "班级" },
      { key: "major_name", label: "专业" },
    ],
    fields: [
      { key: "student_no", label: "学号", type: "text", required: true },
      { key: "real_name", label: "姓名", type: "text", required: true },
      { key: "gender", label: "性别", type: "text" },
      { key: "id_card", label: "身份证号", type: "text" },
      { key: "birth_date", label: "出生日期", type: "date" },
      { key: "phone", label: "手机号", type: "text" },
      { key: "email", label: "邮箱", type: "text" },
      { key: "address", label: "家庭住址", type: "textarea" },
      { key: "class_id", label: "班级ID", type: "number" },
      { key: "major_id", label: "专业ID", type: "number" },
      { key: "college_id", label: "学院ID", type: "number" },
      { key: "enroll_year", label: "入学年份", type: "number" },
      { key: "status", label: "学籍状态", type: "text" },
    ],
  },
  {
    key: "teacher",
    label: "教师",
    columns: [
      { key: "teacher_no", label: "工号" },
      { key: "real_name", label: "姓名" },
      { key: "gender", label: "性别" },
      { key: "title", label: "职称" },
      { key: "college_name", label: "学院" },
    ],
    fields: [
      { key: "teacher_no", label: "工号", type: "text", required: true },
      { key: "real_name", label: "姓名", type: "text", required: true },
      { key: "gender", label: "性别", type: "text" },
      { key: "id_card", label: "身份证号", type: "text" },
      { key: "birth_date", label: "出生日期", type: "date" },
      { key: "phone", label: "手机号", type: "text" },
      { key: "email", label: "邮箱", type: "text" },
      { key: "title", label: "职称", type: "text" },
      { key: "college_id", label: "学院ID", type: "number" },
      { key: "status", label: "状态", type: "text" },
    ],
  },
  {
    key: "college",
    label: "学院",
    columns: [
      { key: "college_name", label: "学院名称" },
      { key: "college_code", label: "学院编码" },
      { key: "description", label: "描述" },
    ],
    fields: [
      { key: "college_name", label: "学院名称", type: "text", required: true },
      { key: "college_code", label: "学院编码", type: "text", required: true },
      { key: "description", label: "描述", type: "textarea" },
    ],
  },
  {
    key: "major",
    label: "专业",
    columns: [
      { key: "major_name", label: "专业名称" },
      { key: "major_code", label: "专业编码" },
      { key: "college_name", label: "学院" },
      { key: "degree_type", label: "学历类型" },
    ],
    fields: [
      { key: "major_name", label: "专业名称", type: "text", required: true },
      { key: "major_code", label: "专业编码", type: "text", required: true },
      { key: "college_id", label: "学院ID", type: "number", required: true },
      { key: "degree_type", label: "学历类型", type: "text" },
      { key: "description", label: "描述", type: "textarea" },
    ],
  },
  {
    key: "class",
    label: "班级",
    columns: [
      { key: "class_name", label: "班级名称" },
      { key: "class_code", label: "班级编码" },
      { key: "head_teacher_name", label: "班主任" },
      { key: "student_count", label: "人数" },
    ],
    fields: [
      { key: "class_name", label: "班级名称", type: "text", required: true },
      { key: "class_code", label: "班级编码", type: "text", required: true },
      { key: "major_id", label: "专业ID", type: "number", required: true },
      { key: "grade_year", label: "入学年份", type: "number" },
      { key: "head_teacher_id", label: "班主任ID", type: "number" },
      { key: "student_count", label: "班级人数", type: "number" },
    ],
  },
  {
    key: "course",
    label: "课程",
    columns: [
      { key: "course_name", label: "课程名称" },
      { key: "course_code", label: "课程编码" },
      { key: "credit", label: "学分" },
      { key: "hours", label: "学时" },
      { key: "course_type", label: "类型" },
    ],
    fields: [
      { key: "course_name", label: "课程名称", type: "text", required: true },
      { key: "course_code", label: "课程编码", type: "text", required: true },
      { key: "credit", label: "学分", type: "number" },
      { key: "hours", label: "学时", type: "number" },
      { key: "course_type", label: "课程类型", type: "text" },
      { key: "college_id", label: "学院ID", type: "number" },
      { key: "description", label: "描述", type: "textarea" },
    ],
  },
];

const tableKey = ref(tableOptions[0].key);
const currentTable = computed(() => {
  return tableOptions.find((option) => option.key === tableKey.value) || tableOptions[0];
});
const currentFields = computed(() => currentTable.value.fields);

const rows = ref<Record<string, any>[]>([]);
const meta = ref<MetaInfo>({ offset: 0, limit: 20, total: 0 });
const loading = ref(false);
const error = ref("");

const page = ref(1);
const pageSize = ref(20);

const keyword = ref("");
const filters = ref<FilterItem[]>([{ key: "", value: "" }]);

const nameMaps = ref<NameMaps>({
  colleges: {},
  majors: {},
  classes: {},
  teachers: {},
});

const modalVisible = ref(false);
const modalMode = ref<"create" | "edit">("create");
const editingId = ref<number | null>(null);
const formState = ref<Record<string, any>>({});
const formLoading = ref(false);
const formError = ref("");

const scoreModalVisible = ref(false);
const scoreLoading = ref(false);
const scoreError = ref("");
const scoreRows = ref<ScoreRow[]>([]);
const scoreStudentName = ref("");

const modalTitle = computed(() => {
  return modalMode.value === "create"
    ? `新增${currentTable.value.label}`
    : `编辑${currentTable.value.label}`;
});

const buildEmptyForm = () => {
  const result: Record<string, any> = {};
  currentFields.value.forEach((field) => {
    result[field.key] = "";
  });
  return result;
};

const updateFormState = (value: Record<string, any>) => {
  formState.value = value;
};

const buildQueryParams = () => {
  const params: Record<string, any> = {
    offset: (page.value - 1) * pageSize.value,
    limit: pageSize.value,
  };
  if (keyword.value.trim()) {
    params.q = keyword.value.trim();
  }
  filters.value.forEach((filter) => {
    if (filter.key && filter.value !== "") {
      params[filter.key] = filter.value;
    }
  });
  return params;
};

const fetchData = async () => {
  loading.value = true;
  error.value = "";
  try {
    const res = await api.get(`/data/${tableKey.value}/list`, {
      params: buildQueryParams(),
    });
    const rawRows = res.data.data || [];
    rows.value = rawRows.map((row: Record<string, any>) => {
      if (tableKey.value === "student") {
        return {
          ...row,
          class_name: row.class_id ? nameMaps.value.classes[row.class_id] || "-" : "-",
          major_name: row.major_id ? nameMaps.value.majors[row.major_id] || "-" : "-",
        };
      }
      if (tableKey.value === "teacher") {
        return {
          ...row,
          college_name: row.college_id ? nameMaps.value.colleges[row.college_id] || "-" : "-",
        };
      }
      if (tableKey.value === "major") {
        return {
          ...row,
          college_name: row.college_id ? nameMaps.value.colleges[row.college_id] || "-" : "-",
        };
      }
      if (tableKey.value === "class") {
        return {
          ...row,
          head_teacher_name: row.head_teacher_id
            ? nameMaps.value.teachers[row.head_teacher_id] || "-"
            : "-",
        };
      }
      return row;
    });
    meta.value = res.data.meta || {
      offset: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      total: rows.value.length,
    };
  } catch (err: any) {
    error.value = err?.response?.data?.message || "数据加载失败，请稍后重试";
    rows.value = [];
  } finally {
    loading.value = false;
  }
};

const fetchAll = async (table: string, limit = 200) => {
  const items: Record<string, any>[] = [];
  let offset = 0;
  while (true) {
    const res = await api.get(`/data/${table}/list`, { params: { offset, limit } });
    const data = res.data.data || [];
    items.push(...data);
    if (data.length < limit) {
      break;
    }
    offset += limit;
  }
  return items;
};

const fetchNameMaps = async () => {
  const results = await Promise.allSettled([
    fetchAll("college"),
    fetchAll("major"),
    fetchAll("class"),
    fetchAll("teacher"),
  ]);
  const nextMaps: NameMaps = {
    colleges: {},
    majors: {},
    classes: {},
    teachers: {},
  };
  if (results[0].status === "fulfilled") {
    results[0].value.forEach((item: Record<string, any>) => {
      nextMaps.colleges[item.id] = item.college_name;
    });
  }
  if (results[1].status === "fulfilled") {
    results[1].value.forEach((item: Record<string, any>) => {
      nextMaps.majors[item.id] = item.major_name;
    });
  }
  if (results[2].status === "fulfilled") {
    results[2].value.forEach((item: Record<string, any>) => {
      nextMaps.classes[item.id] = item.class_name;
    });
  }
  if (results[3].status === "fulfilled") {
    results[3].value.forEach((item: Record<string, any>) => {
      nextMaps.teachers[item.id] = item.real_name;
    });
  }
  nameMaps.value = nextMaps;
};

const applyRouteParams = () => {
  const query = route.query;
  const table = typeof query.table === "string" ? query.table : "";
  if (table && tableOptions.some((item) => item.key === table)) {
    tableKey.value = table;
  }
  const q = typeof query.q === "string" ? query.q : "";
  if (q) {
    keyword.value = q;
  }
  const nextFilters: FilterItem[] = [];
  Object.entries(query).forEach(([key, value]) => {
    if (["table", "q", "page", "pageSize"].includes(key)) {
      return;
    }
    if (typeof value === "string" && value !== "") {
      nextFilters.push({ key, value });
    }
  });
  if (nextFilters.length) {
    filters.value = nextFilters;
  }
  const pageValue = typeof query.page === "string" ? Number(query.page) : 0;
  if (pageValue > 0) {
    page.value = pageValue;
  }
  const pageSizeValue = typeof query.pageSize === "string" ? Number(query.pageSize) : 0;
  if (pageSizeValue > 0) {
    pageSize.value = pageSizeValue;
  }
};

const changeTable = (key: string) => {
  if (tableKey.value === key) {
    return;
  }
  tableKey.value = key;
  page.value = 1;
  keyword.value = "";
  filters.value = [{ key: "", value: "" }];
  formState.value = buildEmptyForm();
  fetchData();
};

const addFilter = () => {
  filters.value = [...filters.value, { key: "", value: "" }];
};

const removeFilter = (index: number) => {
  if (filters.value.length <= 1) {
    filters.value = [{ key: "", value: "" }];
    return;
  }
  filters.value = filters.value.filter((_, idx) => idx !== index);
};

const applyFilters = () => {
  page.value = 1;
  fetchData();
};

const resetFilters = () => {
  keyword.value = "";
  filters.value = [{ key: "", value: "" }];
  page.value = 1;
  fetchData();
};

const handlePageChange = (nextPage: number) => {
  page.value = nextPage;
  fetchData();
};

const handlePageSizeChange = (nextSize: number) => {
  pageSize.value = nextSize;
  page.value = 1;
  fetchData();
};

const openCreate = () => {
  modalMode.value = "create";
  editingId.value = null;
  formError.value = "";
  formState.value = buildEmptyForm();
  modalVisible.value = true;
};

const openEdit = async (row: Record<string, any>) => {
  if (!row?.id) {
    return;
  }
  modalMode.value = "edit";
  editingId.value = row.id;
  formError.value = "";
  formState.value = buildEmptyForm();
  modalVisible.value = true;
  formLoading.value = true;
  try {
    const res = await api.get(`/data/${tableKey.value}/${row.id}`);
    const data = res.data.data || {};
    const result: Record<string, any> = {};
    currentFields.value.forEach((field) => {
      result[field.key] = data[field.key] ?? "";
    });
    formState.value = result;
  } catch (err: any) {
    formError.value = err?.response?.data?.message || "加载详情失败";
  } finally {
    formLoading.value = false;
  }
};

const openScores = async (row: Record<string, any>) => {
  if (!row?.id) {
    return;
  }
  scoreModalVisible.value = true;
  scoreLoading.value = true;
  scoreError.value = "";
  scoreRows.value = [];
  scoreStudentName.value = row.real_name || row.student_no || "学生";
  try {
    const res = await api.get(`/data/student/${row.id}/scores`, {
      params: { offset: 0, limit: 50 },
    });
    scoreRows.value = res.data.data || [];
  } catch (err: any) {
    scoreError.value = err?.response?.data?.message || "成绩加载失败";
  } finally {
    scoreLoading.value = false;
  }
};

const closeScoreModal = () => {
  scoreModalVisible.value = false;
  scoreRows.value = [];
  scoreError.value = "";
};

const closeModal = () => {
  modalVisible.value = false;
  formLoading.value = false;
  formError.value = "";
  editingId.value = null;
};

const normalizePayload = () => {
  const payload: Record<string, any> = {};
  for (const field of currentFields.value) {
    const rawValue = formState.value[field.key];
    if (rawValue === "" || rawValue === null || rawValue === undefined) {
      continue;
    }
    if (field.type === "number") {
      const numberValue = Number(rawValue);
      if (Number.isNaN(numberValue)) {
        throw new Error(`${field.label}必须是数字`);
      }
      payload[field.key] = numberValue;
      continue;
    }
    payload[field.key] = rawValue;
  }
  return payload;
};

const validateForm = () => {
  for (const field of currentFields.value) {
    if (field.required) {
      const value = formState.value[field.key];
      if (value === "" || value === null || value === undefined) {
        throw new Error(`${field.label}不能为空`);
      }
    }
  }
};

const statusClass = (value: string) => {
  const normalized = value?.toString().toLowerCase();
  if (["active", "normal", "enable", "enabled", "在读", "正常"].includes(normalized)) {
    return "ok";
  }
  if (["warning", "risk", "停学", "休学", "异常"].includes(normalized)) {
    return "warn";
  }
  if (["inactive", "disabled", "停用", "毕业", "退学"].includes(normalized)) {
    return "off";
  }
  return "default";
};

const submitForm = async () => {
  formLoading.value = true;
  formError.value = "";
  try {
    validateForm();
    const payload = normalizePayload();
    if (modalMode.value === "create") {
      await api.post(`/data/${tableKey.value}/create`, payload);
    } else {
      if (!editingId.value) {
        throw new Error("缺少编辑目标");
      }
      await api.put(`/data/${tableKey.value}/${editingId.value}`, payload);
    }
    closeModal();
    await fetchData();
  } catch (err: any) {
    formError.value = err?.response?.data?.message || err?.message || "提交失败";
  } finally {
    formLoading.value = false;
  }
};

const removeItem = async (row: Record<string, any>) => {
  if (!row?.id) {
    return;
  }
  const ok = window.confirm(`确认删除该${currentTable.value.label}记录？`);
  if (!ok) {
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    await api.delete(`/data/${tableKey.value}/${row.id}`);
    await fetchData();
  } catch (err: any) {
    error.value = err?.response?.data?.message || "删除失败";
  } finally {
    loading.value = false;
  }
};

onMounted(async () => {
  formState.value = buildEmptyForm();
  applyRouteParams();
  await fetchNameMaps();
  await fetchData();
});
</script>
