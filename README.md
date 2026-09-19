# GRC Helper

把制度文件变成可审计的控制点库。导入 → 解析成条款树 → AI 抽取控制点 → 人工确认 →
映射到合规框架 → 关系图谱、制度冲突、变更影响、审计答复与准备包。

**两条贯穿始终的规矩**：

1. **系统内不存在未经人工确认的正式数据。** AI 只产出提案（`proposals`），
   人在确认队列里逐条裁定之后才写进 `controls` / `mappings` / `control_relations` /
   `policy_conflicts`。
2. **每条结论都要指得回原文。** 控制点记录它出自哪几条条款，引文必须逐字出现在
   那些条款里（自动校验），审计引用给出 `3.4.2` 这样的条款号。

---

## 现在能用到什么程度

**说实话的那一栏更重要。**

| | 状态 |
|---|---|
| 功能范围 | 设计文档划的 L0–L7 加增值能力**全部交付** |
| 语言 | **只支持英文制度**。编号识别、全文检索配置、提示词都按英文来；中文编号（`第五条` / `一、`）不在范围内 |
| 解析层 | 样本语料 6/6；**外部英文文档 29 份里 12 份**能切出可用的条款树。导入前用 `make corpus` 看形状；切错了可以在文档页拆/合并条款 |
| 上层六层（检索/抽取/映射/关系/冲突/准备包） | 在一份外部监管文档上端到端验证过一次，结果可用 |
| 真实审计场景 | **从未验证过**——这是设计文档四条成功标准里唯一没验的一条 |
| 扫描件（无文本层） | **不支持**。解析层没有 OCR（`ocr_pdf` 未接入解析路径，镜像也不含 tesseract/poppler）。扫描件会得到一份空文档加一条警告，请改用带文本层的文件，或在文档页用「粘贴纯文本」录入 |
| 屏幕 | **按桌面端设计**。窄屏（≤768px）下导航会收进抽屉、页面不再错位，但表格、知识图谱、双栏审查在手机上仍然难用——只做到"打得开"，没做到"好用" |
| AI 抽取的稳定性 | **同一份输入两次运行产出不一样**，不要把单次提案数当指标。模型输出不合 schema 是常态：实测一份 37 条款的文档切 7 批、**2 批没抽出东西**（用 minimax-m3）。这类批次现在会在确认队列里留一行、写明原因、可一键重跑，不会再静默消失 |
| AI 成本与预算 | 价格表（`llm/pricing.py`）里没有的模型按 **0** 计，所以「本月花费」是**下限不是实际值**，`monthly_budget_usd` 那道闸门对这类模型形同虚设。总览会直说「本月有 N 次调用未计价」——看到这句话就别信上面那个金额 |
| 开箱状态 | **空库**。上线第一天要先做三件事才能干活：配 AI provider 并绑定任务路由（`/settings/providers` 有「应用到全部推理任务」）、导入合规框架（`make seed-frameworks`）、建至少一条证据类型（`/settings/evidence-types`）。少任何一件，对应的页面会告诉你缺什么、去哪儿补 |

**导入之前先跑一遍解析检查**（见下），别指望任何文风都能吃下去。

---

## 快速开始（开发）

需要 Docker 与 Docker Compose。

```bash
cp .env.example .env
# 生成两个密钥填进 .env：
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # APP_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"                                # JWT_SECRET

make up                 # db / redis / api
docker compose up -d    # 再加上 worker 与前端开发服务器
make migrate
make create-admin email=you@example.com name=You password='至少八位'
```

打开 http://localhost:5173 登录。

**还差一步才有 AI 能力**：进「设置 → AI Provider」加一个 provider（填 base_url 与
API key），再到「任务路由」把八个任务键各绑一个 provider。不绑的话抽取、映射、
冲突检测会直接报路由错误——这是有意的，不会偷偷用默认值。

---

## 部署

**不要把开发机上的 `.env` 拷到生产。** 那两把密钥已经用来加密过开发库里的
provider key、签过开发会话；拷过去等于开发机能解生产的密文。生产环境从
`.env.example` 另起一份，重新生成：

```bash
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # APP_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"                                # JWT_SECRET
# POSTGRES_PASSWORD 设成真的口令，并改 DATABASE_URL 里对应那一段——
# 两个必须一致，一个给数据库建账号，一个给应用连。占位值 CHANGE_ME 或留空，进程会拒绝启动。

make prod-up
make prod-migrate
make prod-create-admin email=you@org.com name=You password='...'
make prod-seed-frameworks   # 导入自带的 NIST CSF 2.0 与 SP 800-53 Rev.5
```

⚠️ **框架那条别写成 `make seed-frameworks`**——那条打的是**开发栈**，在生产上跑
等于什么都没做，而且不会报错：它会另起一套开发栈容器把框架导进开发库，
生产库一条没有。也**只能跑一次**，再跑会以「框架标识已存在」退出 1。

跑完上面四条，库里仍然只有 schema、脱敏规则、阈值和一个 admin。**还有两件要人
在界面上做**，做完系统才真正能干活：

| | 在哪 | 不做会怎样 |
|---|---|---|
| 配 AI provider 并绑定任务路由 | `/settings/providers`，有「应用到全部推理任务」和「设为向量模型」两个按钮 | 抽取、映射、冲突检测全都跑不起来；**漏绑 embedding 最隐蔽**——文档照常解析，但向量不生成，检索静默退化成纯关键字 |
| 建至少一条证据类型 | `/settings/evidence-types` | 证据登记的保存按钮永远是灰的 |

这两件需要人工输入（密钥、机构自己的证据口径），没法做成命令。少任何一件，
对应页面会直接告诉你缺什么、去哪儿补。

默认监听 `8080`（`WEB_PORT` 可改）。生产栈与开发栈的区别不是参数，是**形态**：

- 前端是构建好的静态产物 + nginx，不是 vite 开发服务器
- 后端没有 `--reload`，源码不挂进容器——镜像里是什么就跑什么
- **只有 web 暴露端口**，db / redis / api 都只在内部网络里
- 全部 `restart: unless-stopped`

**没做的事，部署前你得自己补**：HTTPS（前面加一层反代或负载均衡）、
把 `8080` 限制在内网、日志收集、以及下面这条备份的定时任务。

这个仓库按**私有仓**维护。当前树里没有制度原文和机构名，但 git 历史里还有已删
掉的样本痕迹；也没有 LICENSE。不要改成 public。作者邮箱里有本机主机名，
公开之后改不掉。

---

## 备份与恢复

```bash
make backup                                          # 库 + 制度原文卷，落在 backups/
make backup KEEP=30                                  # 多留几份（默认保留最近 14 份）
make restore db=backups/db-....sql docs=backups/docstore-....tar.gz
```

**两样缺一不可**：只备库，原文没了、引用就指向空气；只备原文，人工裁定的结果全丢。
`backups/` 已在 `.gitignore` 里——里面有加密后的 provider 密钥，别提交也别外传。

**要定时，而且要挪到别处。** `make backup` 自己不会跑，也只写在本机——盘坏了两样一起没。
装一条 cron：

```cron
30 2 * * *  cd /srv/grc-helper && make backup >> /var/log/grc-backup.log 2>&1
0  3 * * *  rsync -a /srv/grc-helper/backups/ 备份服务器:/grc/          # 或对象存储
```

超过 `KEEP` 份的旧备份会被自动删掉——无人值守的任务不带轮转，迟早把盘写满，
而盘满之后连新备份都写不成，正好在最需要它的时候没有。

**恢复演练至少做一次。** 没验过的备份等于没有备份。

---

## 主密钥

`APP_SECRET_KEY` 是 Fernet 主密钥，**加密着库里所有 provider 的 API key**。

- **单独备份它**，而且不要和数据库备份放在同一个地方——放一起等于没加密
- **丢了会怎样**：库里的密钥全部解不开。系统本身还能用，但所有 AI 功能会报解密错误，
  要到设置页把每个 provider 的 key 重新填一遍
- **泄露了怎么换**：把新值写进 `.env` 并重启，然后拿**旧**值跑一次轮换——
  库里的密文会被重新加密，不用手工重填：

```bash
make prod-rotate-secret old='旧的 APP_SECRET_KEY'
```

轮换中断了可以直接重跑：已经换过的行会被跳过，不会被改坏。

---

## 登录保护

同一账号 15 分钟内连续失败 5 次就冷却（同一 IP 是 50 次，因为办公网出口共用一个 IP）。
计数放 Redis。**Redis 不可用时限流会静默放行**——这是有意的取舍，
被自己的缓存故障锁在系统外面比"限流暂时失效"更糟。

---

## 换一批制度文档时

```bash
make corpus CORPUS_DIR=/绝对路径/某机构制度
```

**只过解析层，不写任何库**。它会报告每份文件切出多少条款、有没有塌树（一坨吞掉
大半正文）、有没有把正文行当成条款、标题是不是一段正文、编号唯不唯一。
导入之前先跑这个，比导完再发现问题便宜得多。

文风不同导致锚点检查误报时：`CORPUS_ANCHORS="引言,职责分工"` 换一套，
或 `CORPUS_ANCHORS=none` 先跳过。

---

## 验证

```bash
make verify   # pytest / ruff / npm build / make e2e，每条单独报退出码
make test     # 只跑后端，写代码时用这个
```

`ruff` 在 main 上本来就有约 121 条既有告警，`make verify` 只报数不判成败——
看的是有没有比基线多。e2e 跑在隔离的 compose 项目上，跑完自动清理，
不会往开发库里留数据。

---

## 文档

设计文档、实施计划与遗留问题清单在 `docs/`（**独立的本地 git 仓库，不在本仓库里**）。
`docs/open-questions.md` 是这个项目最该先读的一份——它记着每一个已知缺陷、
为什么还没修、以及什么条件下该修。

## 许可

MIT。见 [LICENSE](LICENSE)。
