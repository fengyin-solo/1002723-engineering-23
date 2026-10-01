# 支线驳船模块 · 可复用搭建清单

> 一份清单解决接手翻车三连：三方组件版本对不齐、库里没有驳船/靠泊码头底表、
> 进程拉起来页面读不出载箱量。本地、预发、生产跑的是**同一份**脚本，
> 任何一步没备齐就**停在那一步并打印缺失项**，绝不留下半套环境。

## 一条命令

```bash
make setup        # = bash scripts/bootstrap.sh，一次性备齐并冒烟
make dev          # 本地开发：清单校验 + 前后端进程 + 自动冒烟（含 vite 代理链路）
make smoke BASE_URL=http://x:8000        # 对任意已运行环境补跑冒烟
make verify ENV_A=http://pre ENV_B=http://prod   # 上线前双环境载箱量比对
```

## 清单做了什么（逐步，缺什么停什么）

| 步骤 | 内容 | 没备齐时的表现 |
| --- | --- | --- |
| 1 三方组件 | 校验 Python 3.10+ / Node 18+；后端按 `backend/requirements.txt` **精确锁版本**装进 `.venv`；前端按 `package-lock.json` 用 `npm ci` 精确安装 | 打印缺哪个运行时/哪个包装失败，停止 |
| 2 库表 | 在 SQLite 建 `feeder_barge`（驳船）与 `feeder_berth`（靠泊码头）两张底表，`CREATE TABLE IF NOT EXISTS` 幂等 | 建表失败即停 |
| 3 底表数据 | 导入 `backend/data/fixtures/` 下两份 CSV；导入后**立刻再导一次**验证行数不变 | CSV 非法（载箱量非整数、状态缺分组、码头外键不存在等）整批不入库并逐项报错 |
| 4 后端冒烟 | 起 uvicorn，跑 `scripts/smoke.py`：health 200、列表非空、三类状态齐全、**每条载箱量可读**、静态路由不被 `/{id}` 抢匹配 | 任一不过即停，进程被清理 |
| 5 前端构建 | `npm run build`（vue-tsc 类型检查 + vite 构建） | 编译不过即停 |

## 底表内容

`backend/data/fixtures/feeder_barges.csv` —— 7 条驳船，覆盖三种状态：

| 状态分组 | 驳船 |
| --- | --- |
| 待靠（到港待靠） | FEED-2026-001 / 002 |
| 在港（靠泊中、作业中） | FEED-2026-003（靠泊）/ 004、005（作业） |
| 已离港 | FEED-2026-006 / 007 |

载箱量合计 **915 TEU**（这就是双环境比对的基准值）。
`feeder_berths.csv` —— 4 个靠泊码头 BT-01~04（含维护中/停用各一）。

## 幂等：同一份底表重复导入只认第一次

双层保证，均在 `backend/scripts/seed_import.py`：

1. **文件级**：`seed_import_ledger` 台账按文件内容 sha256 记账，同文件再导整文件跳过；
2. **行级**：即使文件改名/改动，插入也带 `ON CONFLICT(业务编号) DO NOTHING`，
   已存在的驳船编号不会重复插入，第一次导入的内容不被覆盖。

所以清单可以放心反复跑，不会叠出两份驳船。

## 本地开发

```bash
make dev
```

- 先跑一遍 setup（已备齐时秒过），再起后端 `:8000` 与前端 `:5173`；
- 自动跑两遍冒烟：后端直连 + **走前端 vite 代理**（页面真实调用链路）；
- 冒烟不过立即停掉全部进程（按进程组清理，不留 vite/esbuild 孤儿）；
- Ctrl+C 一起退出。页面：<http://127.0.0.1:5173/> → 侧边栏「支线驳船」，
  页头四张统计卡（待靠/在港/已离港/载箱量合计）直接从接口数据计算。

## 上线前：两处环境各跑一遍，载箱量必须相同

```bash
# 预发、生产地址各自冒烟，再逐条比对同编号驳船的载箱量与合计
bash scripts/verify.sh --env-a http://pre.example.com --env-b http://prod.example.com
```

不带参数时在本机起 8000/8001 两个独立库实例自检。
任一处冒烟不过、条数不一致、或同编号载箱量对不上，都会逐项打印差异并非 0 退出。

## 环境变量

见 `.env.example`：`FEEDER_DB_PATH`（库路径，两处环境各自独立）、
`BACKEND_PORT`、`VITE_PROXY_TARGET`、`APP_ENV`。

## 排障记录

所有搭建/开发/核对日志自动归档到 `docs/troubleshooting/logs/`，
已知坑与解法见 [`docs/troubleshooting/troubleshooting.md`](troubleshooting/troubleshooting.md)。
