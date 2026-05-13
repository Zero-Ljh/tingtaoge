# API 与 UI 设计

> 版本：v0.1
> 状态：🟢 已定稿

---

## 1. API 接口

### 1.1 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 返回 Web 首页（static/index.html） |
| POST | `/api/start` | 发起新讨论 |
| GET | `/api/stream/{session_id}` | SSE 流式获取讨论内容 |
| POST | `/api/interject` | 用户插话 |
| POST | `/api/end` | 结束讨论 |
| GET | `/api/report/{session_id}` | 获取讨论报告 |

### 1.2 接口详情

#### POST /api/start

**请求体**：
```json
{
  "topic": "人工智能是否会取代程序员",
  "mode": "debate",          // "debate" | "brainstorm" | "mixed"
  "roles": ["optimist", "skeptic", "ethicist"],  // 可选，不传则自动匹配
  "rounds": 3                 // 可选，默认 3
}
```

**响应**：
```json
{
  "session_id": "uuid",
  "agents": [
    {"id": "A", "name": "技术乐观派", "role": "optimist"},
    {"id": "B", "name": "怀疑论者", "role": "skeptic"},
    {"id": "C", "name": "伦理学者", "role": "ethicist"}
  ],
  "status": "started"
}
```

#### GET /api/stream/{session_id}

SSE 事件流：

```
event: agent_start
data: {"agent_id": "A", "agent_name": "技术乐观派"}

event: agent_chunk
data: {"chunk": "我认为人工智能..."}

event: agent_end
data: {"agent_id": "A", "message": "完整发言内容"}

event: user_interjection
data: {"message": "用户的插话"}

event: status
data: {"round": 2, "phase": "debate"}

event: done
data: {"session_id": "xxx", "report_ready": true}

event: error
data: {"message": "错误描述"}
```

#### POST /api/interject

```json
{
  "session_id": "uuid",
  "message": "我觉得你们忽略了教育成本的问题"
}
```

#### POST /api/end

```json
{
  "session_id": "uuid"
}
```

#### GET /api/report/{session_id}

返回 Markdown 格式的完整报告。

---

## 2. UI 设计

### 2.1 页面布局

不使用任何前端框架，纯原生 HTML/CSS/JS。

```
┌──────────────────────────────────────────────────┐
│  🏯 听涛阁             [辩论] [头脑风暴] [混合]  │  ← 顶栏
│  千涛拍岸，真相自览                              │
├──────────────────────────────────────────────────┤
│                                                  │
│  论题输入框: [___________________________] [开始] │  ← 输入区
│                                                  │
├──────┬──────┬──────┬────────────────────────────┤
│      │      │      │  💬 讨论时间线              │
│ 🤖 A │ 🤖 B │ 🤖 C │                            │  ← 讨论区
│ 乐观  │ 怀疑  │ 伦理  │  A: 我认为...             │
│ 派    │ 论者  │ 学者  │  B: 但你的观点忽略了...   │
│      │      │      │  C: 从伦理角度看...          │
│      │      │      │                            │
│      │      │      │  👤 你觉得教育成本呢？       │
│      │      │      │  A: 这是个好问题...         │
│      │      │      │                            │
├──────┴──────┴──────┴────────────────────────────┤
│  [输入框...                         ] [插话]     │  ← 底栏
│                           [结束讨论] [生成报告]   │
└──────────────────────────────────────────────────┘
```

### 2.2 设计风格

- **色调**：深蓝灰为主（#1a1a2e、#16213e），浅灰文字，营造沉静思辨氛围
- **角色标识**：每个 agent 有对应的浅色（A=青 #00b4d8、B=橙 #f77f00、C=紫 #7b2cbf）
- **字体**：系统字体，无外部字体依赖
- **响应式**：适配桌面和移动端

### 2.3 交互细节

- **流式打字**：Agent 发言时，文字逐字显示，模拟实时思考
- **Agent 头像**：当前发言的 agent 头像高亮/跳动
- **插话**：插话内容在时间线中以不同样式突出显示（用户色）
- **模式标签**：右上角显示当前模式、当前轮次
- **自动滚动**：新内容出现时自动滚动到底部，用户上滚查看时暂停

### 2.4 报告页面

讨论结束后自动过渡到报告展示：
- 顶部：导出按钮（保存 Markdown）
- 主体：渲染后的结构化报告，分段可折叠
