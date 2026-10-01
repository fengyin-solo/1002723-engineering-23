# 支线驳船模块 · 排障记录

搭建/开发/上线核对中踩过的坑统一归档在这里，新坑按同样格式追加。
每次跑脚本的完整日志在 `logs/<bootstrap|dev|verify>-<时间戳>.log`。

---

## T01 · `.venv` 用别的 Python 版本建过，直接失效

- **现象**：接手后 `.venv/bin/python: No such file or directory`、`pip: cannot execute`，
  或 venv 是 Python 3.12 建的、机器上只有 3.11。
- **根因**：venv 内是指向特定解释器路径的符号链接，解释器版本/路径对不上就整个报废。
- **解法**：`bootstrap.sh` 第 1 步会探测当前可用 Python（3.10+），
  venv 缺失或 `import fastapi/uvicorn/pydantic` 失败时**删除重建**，不需要手工处理。

## T02 · Debian/Ubuntu 没有 python3-venv，也没有 sudo

- **现象**：`python3 -m venv` 报 `ensurepip is not available … apt install python3.11-venv`。
- **解法**：脚本兜底走 `venv --without-pip` + 下载 `https://bootstrap.pypa.io/get-pip.py`
  引导 pip，再装锁定依赖。需要本机能访问外网；彻底离线的机器请先装系统包
  `python3.11 python3.11-venv`。

## T03 · 三方组件版本漂移（后人和我装的不一样）

- **现象**：requirements 只写 `fastapi>=0.110`，不同时间装出不同大版本，行为对不齐。
- **解法**：
  - 后端 `backend/requirements.txt` 全部钉死 `==`（含传递依赖），升级时整体回归后再改；
  - 前端提交 `package-lock.json`，清单用 `npm ci` 而不是 `npm install`。

## T04 · npm optional dependencies bug，构建报缺 @rollup/rollup-linux-*-gnu

- **现象**：`npm run build` 报
  `Cannot find module @rollup/rollup-linux-arm64-gnu … npm bug #4828`。
- **根因**：`node_modules` 是别的平台装的（或旧 lock 漏记当前平台的 rollup 原生可选依赖）。
- **解法**：`rm -rf node_modules package-lock.json && npm install` 重新生成干净 lock，
  之后清单走 `npm ci` 即可复现。跨平台（如 mac 装完再到 linux）务必删 node_modules 重装。

## T05 · 库里没有驳船 / 靠泊码头底表

- **现象**：旧实现数据只在进程内存（`app/store.py`），重启即丢；
  或新机器根本没建表，页面列表空。
- **解法**：清单第 2 步 `scripts/init_db.py` 幂等建两张表，
  第 3 步导入 fixtures；`/api/health` 会探测底表存在且非空，
  缺表/空表一律 **HTTP 503** 并写明缺什么，不会假报就绪。

## T06 · 重复导入底表叠出两份

- **现象**：导入脚本多跑一遍，驳船翻倍。
- **解法**：文件级 sha256 台账 + 行级业务唯一键（`barge_code` UNIQUE，
  `ON CONFLICT DO NOTHING`）双保险；清单第 3 步导入后会立刻再导一次校验行数不变。

## T07 · 页面上读不出载箱量

排查顺序（冒烟脚本 `scripts/smoke.py` 自动覆盖）：
1. `GET /api/health` 是否 200 且 `ok=true`（底表在不在、空不空）；
2. `GET /api/feeder` 的 `items[].载箱量` 是否为非负整数（CSV 里写成中文/空串会被导入校验拦下）；
3. 前端是否走到了 vite 代理：`curl http://127.0.0.1:5173/api/feeder`，
   代理目标由 `VITE_PROXY_TARGET` 控制，默认 `http://127.0.0.1:8000`；
4. 驳船页统计卡（待靠/在港/已离港/载箱量合计）直接从列表计算，全是 0 即接口无数据。

## T08 · `/api/feeder/export`、`/berths` 返回 422

- **根因**：静态路由注册在 `/{entry_id}` 后面，`export` 被当成 int 路径参数解析。
- **解法**：路由表中静态路径必须放在动态路径之前（已修），冒烟第 4 项会探这两个地址。

## T09 · 驳船状态能跳步/倒退

- **现象**：到港待靠能直接「确认离港」。
- **解法**：`services/feeder.py` 限定只能沿
  `到港待靠 → 靠泊中 → 作业中 → 已离港` 走相邻一步，跳步、重复、倒退都拒绝并说明原因。

## T10 · 非交互 shell 里后台起 uvicorn 立刻退出

- **现象**：脚本里 `uvicorn ... &` 后日志只有
  `ERROR: [Errno -2] Name or service not known`，端口没监听。
- **解法**：后台启动统一加 `nohup`，并用 `setsid` 放进独立进程组。

## T11 · Ctrl+C / 脚本退出后端口仍被占（vite、esbuild、reloader 孤儿）

- **现象**：`npm run dev` 被杀后 vite/esbuild 子进程仍占 5173；
  `uvicorn --reload` 留下 watchfiles 子进程。
- **解法**：`dev.sh` 用 `setsid` 起进程，退出时 `kill -- -<PGID>` 按进程组一锅端。
  手工清理：`ps -eo pid,args | grep -E 'vite|esbuild|uvicorn'` 后 kill；
  查端口占用：`ss -ltnp | grep -E ':(5173|8000)'`。

## T12 · 上线前两处环境载箱量对不上

- **现象**：同一份清单部署的预发/生产，列表能读但数字不同（底表版本不一致）。
- **解法**：`scripts/verify.sh` 对两处各跑冒烟，并逐条比对驳船编号、条数、载箱量与合计，
  差异逐项打印（例：某编号只在一侧、同编号 120 vs 999、合计 915 vs 1730）。
  基准底表合计：**915 TEU / 7 条**。

## 附：手工排障常用命令

```bash
backend/.venv/bin/python backend/scripts/smoke.py --base-url http://127.0.0.1:8000
backend/.venv/bin/python backend/scripts/smoke.py --base-url http://127.0.0.1:5173   # 带代理链路
curl -s http://127.0.0.1:8000/api/health | backend/.venv/bin/python -m json.tool
# 库坏了想从干净底表重来：
rm backend/data/feeder.sqlite3 && bash scripts/bootstrap.sh
```
