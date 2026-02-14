# AI 评测题库（基于模拟数据）

本文档基于 `scripts/generate_mock_data.py` 的默认逻辑整理，面向以下五类评测能力：
1. 简单查询：单表明细
2. 聚合统计：平均分、通过率、人数统计
3. 排名趋势：TopN、时间变化
4. 复杂过滤：多条件 + 时间范围
5. 异常场景：字段名错误、表名歧义、口语化提问

## 0. 数据前提（判别口径）

默认按脚本 `--seed 42` 推断，核心口径如下：
1. 固定学期：`2025-2026-1`
2. 考勤日期：`2025-09-01`、`2025-09-08`、`2025-09-15`
3. 规模（理论值）：
   - `college=8`
   - `major=64`
   - `class=384`
   - `student=20000`
   - `teacher=1100`
   - `course=300`
   - `course_class=2304`
   - `score=120000`
   - `attendance=360000`
4. 每个学生在该学期应有 6 门成绩（由班级 6 门课生成）

---

## 1. 简单查询（单表明细）

### Q1
问题：查询学号 `S00001` 的学生档案。

```sql
SELECT
  s.id, s.student_no, s.real_name, s.gender, s.birth_date,
  s.phone, s.email, s.class_id, s.major_id, s.college_id,
  s.enroll_year, s.status
FROM student s
WHERE s.is_deleted = 0
  AND s.student_no = 'S00001';
```

### Q2
问题：查询课程编码 `K0100` 的课程明细。

```sql
SELECT
  c.id, c.course_code, c.course_name, c.credit, c.hours,
  c.course_type, c.college_id, c.description
FROM course c
WHERE c.is_deleted = 0
  AND c.course_code = 'K0100';
```

### Q3
问题：查询班级编码 `CLM0011` 的班级明细。

```sql
SELECT
  c.id, c.class_code, c.class_name, c.major_id,
  c.grade_year, c.head_teacher_id, c.student_count
FROM `class` c
WHERE c.is_deleted = 0
  AND c.class_code = 'CLM0011';
```

---

## 2. 聚合统计（平均分、通过率、人数）

### Q1
问题：统计 `2025-2026-1` 学期全校平均分与通过率（>=60）。

```sql
SELECT
  ROUND(AVG(sc.score_value), 2) AS avg_score,
  ROUND(SUM(CASE WHEN sc.score_value >= 60 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS pass_rate_pct,
  COUNT(*) AS score_rows
FROM score sc
WHERE sc.is_deleted = 0
  AND sc.term = '2025-2026-1';
```

### Q2
问题：按入学年份统计在读学生人数。

```sql
SELECT
  s.enroll_year,
  COUNT(*) AS student_count
FROM student s
WHERE s.is_deleted = 0
  AND s.status = '在读'
GROUP BY s.enroll_year
ORDER BY s.enroll_year;
```

### Q3
问题：校验基础规模统计（sanity check）。

```sql
SELECT
  (SELECT COUNT(*) FROM college WHERE is_deleted = 0) AS college_cnt,
  (SELECT COUNT(*) FROM major WHERE is_deleted = 0) AS major_cnt,
  (SELECT COUNT(*) FROM `class` WHERE is_deleted = 0) AS class_cnt,
  (SELECT COUNT(*) FROM student WHERE is_deleted = 0) AS student_cnt,
  (SELECT COUNT(*) FROM teacher WHERE is_deleted = 0) AS teacher_cnt,
  (SELECT COUNT(*) FROM course WHERE is_deleted = 0) AS course_cnt,
  (SELECT COUNT(*) FROM course_class WHERE is_deleted = 0) AS course_class_cnt,
  (SELECT COUNT(*) FROM score WHERE is_deleted = 0) AS score_cnt,
  (SELECT COUNT(*) FROM attendance WHERE is_deleted = 0) AS attendance_cnt;
```

判别参考：应分别接近/等于 `8,64,384,20000,1100,300,2304,120000,360000`。

---

## 3. 排名趋势（TopN、时间变化）

### Q1
问题：`2025-2026-1` 学期专业平均分 Top10。

```sql
SELECT
  m.major_code,
  m.major_name,
  ROUND(AVG(sc.score_value), 2) AS avg_score,
  COUNT(*) AS sample_cnt
FROM score sc
JOIN student st ON st.id = sc.student_id AND st.is_deleted = 0
JOIN major m ON m.id = st.major_id AND m.is_deleted = 0
WHERE sc.is_deleted = 0
  AND sc.term = '2025-2026-1'
GROUP BY m.id, m.major_code, m.major_name
ORDER BY avg_score DESC, sample_cnt DESC
LIMIT 10;
```

### Q2
问题：`2025-2026-1` 学期挂科率最高班级 Top10。

```sql
SELECT
  c.class_code,
  c.class_name,
  ROUND(SUM(CASE WHEN sc.score_value < 60 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS fail_rate_pct,
  COUNT(*) AS sample_cnt
FROM score sc
JOIN course_class cc ON cc.id = sc.course_class_id AND cc.is_deleted = 0
JOIN `class` c ON c.id = cc.class_id AND c.is_deleted = 0
WHERE sc.is_deleted = 0
  AND sc.term = '2025-2026-1'
GROUP BY c.id, c.class_code, c.class_name
ORDER BY fail_rate_pct DESC, sample_cnt DESC
LIMIT 10;
```

### Q3
问题：2025年9月考勤出勤率趋势（按日期）。

```sql
SELECT
  a.attend_date,
  COUNT(*) AS total_cnt,
  SUM(CASE WHEN a.status = '出勤' THEN 1 ELSE 0 END) AS present_cnt,
  ROUND(SUM(CASE WHEN a.status = '出勤' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS attendance_rate_pct
FROM attendance a
WHERE a.is_deleted = 0
  AND a.attend_date BETWEEN '2025-09-01' AND '2025-09-30'
GROUP BY a.attend_date
ORDER BY a.attend_date;
```

---

## 4. 复杂过滤（多条件 + 时间范围）

### Q1
问题：查询“信息工程学院 2024级”在 2025年9月 的异常考勤（迟到/缺勤/早退）。

```sql
SELECT
  st.student_no,
  st.real_name,
  c.class_name,
  col.college_name,
  a.attend_date,
  a.status
FROM attendance a
JOIN student st ON st.id = a.student_id AND st.is_deleted = 0
JOIN `class` c ON c.id = st.class_id AND c.is_deleted = 0
JOIN college col ON col.id = st.college_id AND col.is_deleted = 0
WHERE a.is_deleted = 0
  AND col.college_name = '三峡科技MOCK大学信息工程学院'
  AND c.grade_year = 2024
  AND a.attend_date BETWEEN '2025-09-01' AND '2025-09-30'
  AND a.status IN ('迟到', '缺勤', '早退')
ORDER BY a.attend_date, st.student_no;
```

### Q2
问题：查询专业编码 `M010`、必修课、成绩低于60分的学生成绩明细。

```sql
SELECT
  st.student_no,
  st.real_name,
  m.major_code,
  m.major_name,
  co.course_code,
  co.course_name,
  sc.score_value,
  sc.score_level,
  sc.term
FROM score sc
JOIN student st ON st.id = sc.student_id AND st.is_deleted = 0
JOIN major m ON m.id = st.major_id AND m.is_deleted = 0
JOIN course co ON co.id = sc.course_id AND co.is_deleted = 0
WHERE sc.is_deleted = 0
  AND sc.term = '2025-2026-1'
  AND m.major_code = 'M010'
  AND co.course_type = '必修'
  AND sc.score_value < 60
ORDER BY sc.score_value ASC, st.student_no;
```

### Q3
问题：查询“管理学院 + 2023级 + 分数70~85 + 学分>=3”的成绩明细。

```sql
SELECT
  st.student_no,
  st.real_name,
  c.class_name,
  co.course_code,
  co.course_name,
  co.credit,
  sc.score_value
FROM score sc
JOIN student st ON st.id = sc.student_id AND st.is_deleted = 0
JOIN `class` c ON c.id = st.class_id AND c.is_deleted = 0
JOIN college col ON col.id = st.college_id AND col.is_deleted = 0
JOIN course co ON co.id = sc.course_id AND co.is_deleted = 0
WHERE sc.is_deleted = 0
  AND sc.term = '2025-2026-1'
  AND col.college_name = '三峡科技MOCK大学管理学院'
  AND c.grade_year = 2023
  AND sc.score_value BETWEEN 70 AND 85
  AND co.credit >= 3
ORDER BY sc.score_value DESC, st.student_no;
```

---

## 5. 异常场景（字段错误、歧义、口语化）

### Q1（字段名错误映射）
问题：查“学员编号 `S00123`”的六门课成绩（应映射为 `student_no`）。

```sql
SELECT
  st.student_no,
  st.real_name,
  co.course_code,
  co.course_name,
  sc.score_value,
  sc.score_level
FROM score sc
JOIN student st ON st.id = sc.student_id AND st.is_deleted = 0
JOIN course co ON co.id = sc.course_id AND co.is_deleted = 0
WHERE sc.is_deleted = 0
  AND sc.term = '2025-2026-1'
  AND st.student_no = 'S00123'
ORDER BY co.course_code;
```

### Q2（表名/口径歧义）
问题：统计每个班级人数（声明人数 vs 实际学生数）。

```sql
SELECT
  c.class_code,
  c.class_name,
  c.student_count AS declared_count,
  COUNT(st.id) AS actual_count
FROM `class` c
LEFT JOIN student st
  ON st.class_id = c.id
 AND st.is_deleted = 0
WHERE c.is_deleted = 0
GROUP BY c.id, c.class_code, c.class_name, c.student_count
ORDER BY c.class_code;
```

### Q3（口语化提问）
问题：挂科最多的前10个班级。

```sql
SELECT
  c.class_code,
  c.class_name,
  SUM(CASE WHEN sc.score_value < 60 THEN 1 ELSE 0 END) AS fail_cnt,
  COUNT(*) AS total_cnt,
  ROUND(SUM(CASE WHEN sc.score_value < 60 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS fail_rate_pct
FROM score sc
JOIN course_class cc ON cc.id = sc.course_class_id AND cc.is_deleted = 0
JOIN `class` c ON c.id = cc.class_id AND c.is_deleted = 0
WHERE sc.is_deleted = 0
  AND sc.term = '2025-2026-1'
GROUP BY c.id, c.class_code, c.class_name
ORDER BY fail_cnt DESC, fail_rate_pct DESC
LIMIT 10;
```

