# 框架种子数据

| 文件 | 来源 | 许可 |
|---|---|---|
| `nist-csf-2.0.csv` | NIST Cybersecurity Framework 2.0 | 美国政府作品，公有领域 |
| `nist-800-53-r5.csv` | NIST SP 800-53 Rev.5 + Rev.5 baselines | 美国政府作品，公有领域 |

ISO/IEC 27001:2022 Annex A **不在此目录**：其正文受 ISO 版权保护，不可随仓库分发。
请按 `app/frameworks/template.py` 的列定义自行准备后上传。

CSV 由 `convert_csf.py` / `convert_800_53.py` 从 NIST 官方发布文件生成，
脚本仅用于记录来源与可复现性，**不在运行时联网**。
