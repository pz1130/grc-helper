// Mock data handler for offline / demo preview mode

export interface MockUser {
  id: number;
  email: string;
  name: string;
  role: "admin" | "grc_lead" | "contributor" | "viewer";
}

export const DEMO_USER: MockUser = {
  id: 1,
  email: "admin@example.com",
  name: "GRC Demo",
  role: "admin",
};

export const DEMO_TOKEN = "demo-mock-token";

export function getMockResponse(path: string, _init: RequestInit = {}, language = "zh"): unknown {
  const url = path.split("?")[0];
  const pick = (zh: string, en: string) => language.startsWith("zh") ? zh : en;

  if (url === "/api/auth/me") {
    return DEMO_USER;
  }

  if (url === "/api/auth/login") {
    return {
      access_token: DEMO_TOKEN,
      user: DEMO_USER,
    };
  }

  if (url === "/api/settings/usage") {
    return {
      month_to_date_cost: 142.8,
      budget: 500.0,
      by_task: [
        { task_key: "clause_extraction", cost: 72.4, calls: 1420 },
        { task_key: "framework_mapping", cost: 48.2, calls: 980 },
        { task_key: "gap_analysis", cost: 22.2, calls: 360 },
      ],
    };
  }

  if (url === "/api/evidence/stats") {
    return { expired: 3 };
  }

  if (url === "/api/proposals/stats") {
    return {
      pending: 4,
      by_kind: { extraction: 2, mapping: 2 },
    };
  }

  if (url === "/api/documents") {
    return [
      {
        id: 1,
        title: pick("企业信息安全总体方针与管理办法", "Enterprise Information Security Policy"),
        doc_type: "policy",
        status: "active",
        version: "v3.2",
        owner: "CISO Office",
        effective_date: "2024-01-01",
        review_due_date: "2026-09-01",
        original_filename: "security_policy_2024.docx",
        parse_error: null,
        parse_warnings: null,
        ocr_quality_flag: false,
      },
      {
        id: 2,
        title: pick("用户身份鉴别与访问控制技术规范", "Identity and Access Control Standard"),
        doc_type: "standard",
        status: "active",
        version: "v2.1",
        owner: "IAM Team",
        effective_date: "2024-06-01",
        review_due_date: "2026-10-15",
        original_filename: "iam_access_spec.pdf",
        parse_error: null,
        parse_warnings: null,
        ocr_quality_flag: false,
      },
      {
        id: 3,
        title: pick("数据跨境流动与敏感信息防泄漏规约", "Cross-border Data Transfer and DLP Guideline"),
        doc_type: "guideline",
        status: "draft",
        version: "v1.4",
        owner: "Compliance Legal",
        effective_date: "2025-01-15",
        review_due_date: "2026-11-20",
        original_filename: "cross_border_data_transfer.pdf",
        parse_error: null,
        parse_warnings: null,
        ocr_quality_flag: false,
      },
      {
        id: 4,
        title: pick("生产环境特权账号生命周期管理细则", "Production Privileged Account Lifecycle Procedure"),
        doc_type: "procedure",
        status: "active",
        version: "v2.0",
        owner: "DevOps Ops",
        effective_date: "2024-09-01",
        review_due_date: "2026-12-10",
        original_filename: "privileged_account_lifecycle.docx",
        parse_error: null,
        parse_warnings: null,
        ocr_quality_flag: false,
      },
    ];
  }

  if (url === "/api/documents/coverage") {
    return [
      { document_id: 1, clauses: 42, normative_clauses: 36, controls: 32, proposals: 4, uncovered_normative: 4, never_extracted: false },
      { document_id: 2, clauses: 28, normative_clauses: 24, controls: 22, proposals: 2, uncovered_normative: 2, never_extracted: false },
      { document_id: 3, clauses: 15, normative_clauses: 12, controls: 0, proposals: 0, uncovered_normative: 12, never_extracted: true },
      { document_id: 4, clauses: 19, normative_clauses: 18, controls: 18, proposals: 1, uncovered_normative: 0, never_extracted: false },
    ];
  }

  if (url === "/api/frameworks") {
    return [
      { id: 1, code: "nist-csf-2.0", name: pick("NIST 网络安全框架 2.0 (CSF 2.0)", "NIST Cybersecurity Framework 2.0 (CSF 2.0)"), version: "2.0", publisher: "nist.gov", total_controls: 106 },
      { id: 2, code: "nist-800-53-r5", name: "NIST SP 800-53 Rev.5", version: "5.1.1", publisher: "nist.gov", total_controls: 1189 },
      { id: 3, code: "iso-27001-2022", name: pick("ISO/IEC 27001:2022 信息安全管理体系", "ISO/IEC 27001:2022 Information Security Management Systems"), version: "2022", publisher: "iso.org", total_controls: 93 },
    ];
  }

  if (url === "/api/controls") {
    return [
      { id: 1, code: "AC-1", title: pick("访问控制策略与规程", "Access Control Policy and Procedures"), category: pick("访问控制", "Access Control"), status: "implemented", description: pick("建立、分发并审查组织范围内的访问控制策略与配套实施流程。", "Establish, distribute and review organization-wide access control policies and procedures.") },
      { id: 2, code: "IA-2", title: pick("身份识别与鉴别（组织级）", "Identification and Authentication"), category: pick("身份与鉴别", "Identification & Authentication"), status: "in_progress", description: pick("所有内部网络和特权账户访问均须启用抗钓鱼多因素认证（MFA）。", "Require phishing-resistant multifactor authentication for internal network and privileged account access.") },
      { id: 3, code: "SC-7", title: pick("边界防护与微隔离机制", "Boundary Protection and Microsegmentation"), category: pick("系统与通信", "System & Communications"), status: "implemented", description: pick("在关键业务系统之间实施零信任微隔离和深层数据包检测。", "Apply zero-trust microsegmentation and deep packet inspection between critical business systems.") },
      { id: 4, code: "SI-4", title: pick("信息系统监控与入侵检测", "System Monitoring and Intrusion Detection"), category: pick("系统完整性", "System Integrity"), status: "implemented", description: pick("全天候收集生产集群系统日志与审计记录，并接入 SIEM 告警中心。", "Continuously collect production system logs and audit trails and route them to the SIEM alerting center.") },
    ];
  }

  if (url === "/api/tech-assets") {
    return [
      { id: 1, name: "AWS Production Cloud VPC (ap-east-1)", category: "Network", criticality: "high", owner: "DevOps Team", status: "active" },
      { id: 2, name: "Core Financial DB Cluster (PostgreSQL + pgvector)", category: "Database", criticality: "critical", owner: "Data Platform", status: "active" },
      { id: 3, name: "SSO & IAM Identity Provider (Keycloak)", category: "Identity", criticality: "critical", owner: "SecOps Team", status: "active" },
      { id: 4, name: "Kubernetes Enterprise Workload Cluster", category: "Compute", criticality: "high", owner: "Infra Team", status: "active" },
    ];
  }

  if (url === "/api/evidence") {
    return [
      { id: 1, title: pick("2026 Q3 堡垒机审计记录与跳板机访问回放", "2026 Q3 Bastion Host Audit and Session Replay"), status: "valid", control_code: "AC-1", expires_at: "2026-12-31" },
      { id: 2, title: pick("生产数据库 SSL 泛域名证书轮换工单", "Production Database SSL Wildcard Certificate Rotation"), status: "expired", control_code: "SC-7", expires_at: "2026-08-15" },
      { id: 3, title: pick("第三方渗透测试评估总结报告（2026）", "Third-party Penetration Test Report (2026)"), status: "valid", control_code: "SI-4", expires_at: "2027-03-01" },
    ];
  }

  if (url === "/api/proposals") {
    return [
      { id: 101, kind: "mapping", source_text: pick("第 4.2 条：所有进入生产机房的人员须经双人复核并留痕", "Clause 4.2: Production data-center access requires dual approval and an audit trail."), target_framework: "NIST CSF 2.0 PR.AC-1", confidence: 0.94, status: "pending" },
      { id: 102, kind: "extraction", source_text: pick("第 7.1 条：静态数据与传输数据均应采用 AES-256 或同等级别加密", "Clause 7.1: Data at rest and in transit must use AES-256 or equivalent encryption."), target_framework: "ISO 27001 A.10.1", confidence: 0.89, status: "pending" },
    ];
  }

  if (url === "/api/settings/providers") {
    return [
      { id: 1, name: "OpenAI Production", base_url: "https://api.openai.com/v1", model: "gpt-4o", masked_key: "sk-proj-****89Ab", is_active: true },
      { id: 2, name: "Anthropic Claude Dedicated", base_url: "https://api.anthropic.com/v1", model: "claude-3-5-sonnet", masked_key: "sk-ant-****55Ff", is_active: true },
    ];
  }

  if (url === "/api/settings/users") {
    return [
      { id: 1, email: "admin@example.com", name: "Admin (Demo)", role: "admin", is_active: true },
      { id: 2, email: "lead@example.com", name: "GRC Lead", role: "grc_lead", is_active: true },
      { id: 3, email: "auditor@example.com", name: "External Auditor", role: "viewer", is_active: true },
    ];
  }

  if (url === "/api/settings/redaction") {
    return { enabled: true, rules: ["chinese_id_card", "phone_number", "credit_card", "api_key", "email"] };
  }

  if (url === "/api/settings/thresholds") {
    return { min_confidence: 0.85, require_human_review: true, high_risk_auto_escalate: true };
  }

  if (url === "/api/settings/audit-log") {
    return [
      { id: 1, actor: "admin@example.com", action: "UPDATE_LLM_CONFIG", target: "Provider: OpenAI Production", timestamp: "2026-09-17T18:30:00Z" },
      { id: 2, actor: "system", action: "SCHEDULED_EVIDENCE_SWEEP", target: "Evidence #2 marked as EXPIRED", timestamp: "2026-09-17T00:00:00Z" },
    ];
  }

  if (url === "/api/search") {
    return [];
  }

  return [];
}
