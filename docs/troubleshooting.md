# 排障记录归档

支线驳船模块搭建与上线的排障记录统一归档在这里。
新记录按文末模板追加，写清现象、定位、处置、验证四要素。

## 记录格式

```
### YYYY-MM-DD 标题
- 现象：
- 定位：
- 处置：
- 验证：
```

---

### 2026-10-01 `.venv` 跨机器拷贝，进程根本拉不起来
- 现象：`backend/run.sh` 报 `.venv/bin/pip: cannot execute: required file not found`，后端起不来。
- 定位：`.venv/pyvenv.cfg` 里的 `executable` 指向他机路径
  （`/Users/syj/.../cpython-3.12.14-macos-aarch64`），是 macOS + Python 3.12 建的环境，
  本机是 Linux + Python 3.11，解释器不存在。
- 处置：`scripts/setup.sh` 第 2 步先验活（`.venv/bin/python -c ''`），跑不起来就重建；
  `run.sh` 同样加了验活逻辑，不再直接踩坑。
- 验证：`.venv/bin/python -c 'import fastapi'` 通过，`make setup` 走完五步。

### 2026-10-01 系统缺 `ensurepip`，venv 建到一半失败
- 现象：`python3 -m venv .venv` 报 `ensurepip is not available`，留下半个 `.venv`。
- 定位：Debian/Ubuntu 未装 `python3-venv` 包，venv 无法自带 pip。
- 处置：清单兜底 `python3 -m venv --without-pip` + `get-pip.py` 引导 pip；
  失败前会先删掉半个 `.venv`，不留残局。
- 验证：`scripts/setup.sh --deps-only` 退出码 0，`.venv/bin/pip --version` 有输出。

### 2026-10-01 底表缺「已离港」、载箱量是占位文本，页面读不出载箱量
- 现象：驳船列表只有 到港待靠/靠泊中/作业中 三条样例，载箱量列显示「支线驳船样例N」，
  页面上读不出真实载箱量。
- 定位：feeder 的样例数据混在 `app/seed.py` 里，既无已离港状态，载箱量也不是数字。
- 处置：feeder 底表从 seed 迁出，统一由 `backend/data/feeder_base.csv` 提供，
  进程启动时经 `app/importer.py` 校验并幂等导入；缺状态覆盖或载箱量非数字直接拒导。
- 验证：`python -m app.importer check data/feeder_base.csv` 通过；
  `make smoke` 输出四条驳船且载箱量全部为数字。

---

### YYYY-MM-DD （模板）标题
- 现象：
- 定位：
- 处置：
- 验证：
