# 港口集装箱作业管理平台

面向港口集装箱码头船舶靠离泊、岸桥装卸、堆场翻倒、闸口进出与危险品申报的一体化作业管理后台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 快速开始（推荐）

支线驳船模块有一份可复用搭建清单：一次备齐三方组件、驳船/靠泊码头底表与冒烟，
任何一步没备齐就停在那一步并打印缺失项。本地 / 预发 / 生产同一份脚本。

```bash
make setup     # 一次性搭建：锁版本依赖 → 建 SQLite 底表 → 幂等导入驳船底表 → 冒烟 → 前端构建
make dev       # 本地开发：清单校验后拉起前后端，自动跑冒烟（含 vite 代理链路）
make verify ENV_A=http://pre ENV_B=http://prod   # 上线前双环境载箱量一致性比对
```

详见 [`docs/feeder-bootstrap.md`](docs/feeder-bootstrap.md)，排障记录归档在
[`docs/troubleshooting/troubleshooting.md`](docs/troubleshooting/troubleshooting.md)。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   ├── app/store.py          其余模块的内存示例数据
│   ├── app/db.py             支线驳船 SQLite 底表访问层
│   ├── scripts/              建表 / 幂等导入 / 冒烟 / 双环境比对
│   └── data/fixtures/        驳船与靠泊码头底表 CSV
├── scripts/                  bootstrap.sh / dev.sh / verify.sh 搭建清单
└── docs/                     搭建清单说明与排障归档
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 泊位计划 | `berth` | 泊位 | 泊位编号、泊位长度、水深条件 |
| 船舶作业 | `vessel` | 船舶 | 船舶编号、船名、船公司 |
| 岸桥调度 | `quaycrane` | 岸桥 | 岸桥编号、岸桥型号、额定起重量 |
| 堆场策划 | `yardplan` | 箱位 | 箱位编号、所在箱区、贝位号 |
| 场桥调度 | `rtg` | 场桥 | 场桥编号、场桥型号、作业箱区 |
| 内集卡调度 | `truck` | 内集卡 | 集卡编号、车牌号码、所属车队 |
| 集装箱信息 | `container` | 集装箱 | 箱号、箱型尺寸、箱主代码 |
| 闸口管理 | `gate` | 进出闸 | 闸口编号、闸口类型、车道编号 |
| 危险品申报 | `dangerous` | 危险品 | 申报编号、箱号、危品类别 |
| 冷藏箱监控 | `coldchain` | 冷藏箱 | 冷藏箱号、设定温度、当前温度 |
| 绑扎加固 | `lashing` | 绑扎任务 | 绑扎编号、对应船舶、箱位范围 |
| 工班管理 | `shift` | 工班 | 工班编号、工班名称、当班组长 |
| 箱体修洗 | `repair` | 修洗任务 | 任务编号、箱号、损伤类型 |
| 理货记录 | `tally` | 理货记录 | 理货编号、对应船舶、箱量核对 |
| 海关查验 | `customs` | 查验记录 | 查验编号、箱号、查验类型 |
| 支线驳船 | `feeder` | 驳船 | 驳船编号、驳船名称、运营公司 |
| 超限箱管理 | `oog` | 超限箱 | 超限箱号、箱型尺寸、超限方向 |
| 空箱堆存 | `emptystack` | 空箱 | 空箱编号、箱主代码、箱型尺寸 |
| 能耗监测 | `energy` | 能耗记录 | 记录编号、设备类型、设备编号 |
| 安全巡检 | `safetycheck` | 巡检记录 | 巡检编号、巡检区域、巡检日期 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。
