# GRC Helper

给不同组织的 IT GRC 人员用的制度治理助手：导入制度文件 → 解析成条款树 → AI 抽取控制点 →
映射到合规框架 → 关系/冲突/变更影响 → 审计答复与准备包。

## 验证

```bash
make verify        # 四条检查一次跑完：pytest / ruff / npm build / make e2e
make test          # 只跑后端，快，写代码时用这个
```

`make verify` 的三件事要知道：

- **每条单独报退出码，失败不中断后面的**——一次跑完能看到所有失败，不是第一个。
  绝不要把验证命令管道给 `tail`：报的是 `tail` 的退出码。2026-09-11 就这样同时藏过
  一次 playwright 失败和 ruff 的 126 条，两个都显示为绿。
- **ruff 只报数不判成败**。main 上本来就有 **121** 条既有告警（多是 `app/llm/router.py`
  与 `app/ingest/router.py` 的 B008）。只看本次改动的文件有没有新增，别去清基线。
- **e2e 走隔离的 compose 项目**（`make e2e`，跑完 `down -v`），所以慢几分钟。
  不要直接 `npx playwright test`——那跑在开发栈上，每次留下一个 provider 和一个用户。
  中途 Ctrl-C 打断了用 `make e2e-down` 收尾。

## 换一批制度文档时

```bash
make corpus CORPUS_DIR=/abs/path/某机构制度
make corpus CORPUS_DIR=/abs/path CORPUS_ANCHORS="引言,职责分工"   # 换一套文风锚点
make corpus CORPUS_DIR=/abs/path CORPUS_ANCHORS=none             # 还不知道就先跳过
```

**只过解析层，不写任何库**——导入之前先看条款树切不切得开、有没有目录行混进条款、
编号还原对不对。路径必须绝对（docker 的 bind mount 不认相对路径，也不展开 `~`）。

`CORPUS_ANCHORS` 的默认值（`Introduction` / `Roles and Responsibilities`）是
**样本那批文档的文风**，不是解析器的性质。拿它去量别家机构的文档，失败的是「文风不同」
而不是「解析漏了开头」。

## 两条铁律

1. **`controls` / `mappings` / `control_relations` / `policy_conflicts` 只能经
   `backend/app/review/materialize.py` 写入。** AI 任务只产 `Proposal`，人工确认后才落正式表。
   控制点的人工编辑（`update_control`）与合并（`merge_controls`）也在那个模块里，同一把
   `lock_control_writes` 咨询锁下。
2. **对已确认数据的每一次改动都要留审计。** `AuditLog` 按 id 记录实体，所以**不删行**：
   控制点合并是 `status='merged'` + `merged_into_id`，不是 DELETE。

## 文档在哪

| | |
|---|---|
| `docs/superpowers/specs/` | 设计文档，`2026-09-08-grc-helper-design.md` 是总设计（范围 L0–L7） |
| `docs/superpowers/plans/` | 逐里程碑的实施计划，TDD 步骤 |
| `docs/open-questions.md` | 遗留问题。**开头那节「判定原则」先读**——它决定一条问题还算不算数 |

计划里的复选框**不按习惯维护**（M1 是 0/144 但早已完成）。未勾的框不是"没做完"的证据，
找对应的 `docs: record M<n> acceptance` 提交。

## 开发库的性质

开发库里是 6 份样本制度，全部来自同一家机构、同一种文风。**这批语料迟早整批换掉**，
所以「把开发库里这 N 条数据改对」没有长期价值——要改的是换一批文档仍然成立的机制
（解析器、提示词、配对逻辑、检测）。`docs/open-questions.md` 就是按这把尺子重估过的。

## 一个反复出现的坑

切过分支后整个 spec 文件变红，先 `docker compose restart web` 再判断——
Docker 里的 vite 会因文件增删而失效，那通常不是回归。
