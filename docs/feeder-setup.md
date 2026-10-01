# 支线驳船模块搭建清单

接手支线驳船（feeder）模块时，按这一份清单走：五步全部通过才算就绪，
哪一步缺东西就停在哪一步并打印缺失项，不会留下半套环境。

## 一键执行

```bash
make setup          # 全流程：工具链 → 三方组件 → 底表 → 起进程 → 冒烟
make setup 之后可用：
make smoke          # 只对已运行的后端再跑一遍冒烟
make test           # 底表导入的回归用例（校验拦截 + 幂等）
```

## 五步清单

| 步骤 | 做什么 | 缺什么会停 | 怎么补 |
| --- | --- | --- | --- |
| 1/5 工具链 | 校验 python3≥3.10、node≥18、npm | 未安装或版本不够 | 装齐后重跑 |
| 2/5 三方组件 | 验活并重建后端 `.venv`，按 `requirements.lock` 安装；前端按 `package-lock.json` `npm ci` | `.venv` 跨机器拷贝跑不起来、`ensurepip` 缺失、锁文件缺失 | 脚本自动重建 venv（`ensurepip` 缺失时用 get-pip.py 兜底）；锁文件缺失先补齐 |
| 3/5 驳船底表 | 校验 `backend/data/feeder_base.csv`：列齐全、状态覆盖 待靠/在港/已离港、载箱量为数字；再连导两次验证幂等 | 缺列、缺状态、载箱量非数字、编号重复 | 按打印的缺失项修底表 |
| 4/5 起进程 | 后台拉起 uvicorn，30s 内等 `/api/health` | 端口被占、底表在启动导入时被拒 | 看 `/tmp/feeder-backend.log` |
| 5/5 冒烟 | 读 `/api/feeder`：列表非空、状态覆盖三类、每条载箱量可读，输出指纹 | 列表为空、载箱量读不出 | 回到第 3 步查底表 |

## 底表与幂等约定

- 底表只有一份：`backend/data/feeder_base.csv`，列固定为
  驳船编号、驳船名称、运营公司、载箱量、到港时间、离港时间、靠泊码头、驳船状态。
- 进程启动时（`app/main.py` 的 lifespan）经 `app/importer.py` 导入；
  底表缺失或校验不过，进程直接起不来，不会带病上岗。
- 导入按 **驳船编号** 去重：同一份底表重复导入只认第一次，
  第二次新增 0 条、全部跳过，列表不会叠出两份。
- 手工验证：`cd backend && .venv/bin/python -m app.importer dryrun data/feeder_base.csv`

## 上线前：两处环境各跑一遍

```bash
scripts/compare_env.sh http://环境A:8000 http://环境B:8000
```

脚本对两处环境分别跑冒烟，比对 `(驳船编号, 载箱量)` 指纹：
一致才放行；不一致会逐行打出差异，先排障再上线。

## 排障记录

踩过的坑统一归档到 [troubleshooting.md](troubleshooting.md)，新增记录按文末模板追加。
