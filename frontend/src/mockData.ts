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
  name: "Admin (Demo Mode)",
  role: "admin",
};

export const DEMO_TOKEN = "demo-mock-token";

export function getMockResponse(path: string, _init: RequestInit = {}): unknown {
  const url = path.split("?")[0];

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
        title: "企业信息安全总体方针与管理办法",
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
        title: "用户身份鉴别与访问控制技术规范",
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
        title: "数据跨境流动与敏感信息防泄漏规约",
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
        title: "生产环境特权账号生命周期管理细则",
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
      { id: 1, code: "nist-csf-2.0", name: "NIST 网络安全框架 2.0 (CSF 2.0)", version: "2.0", publisher: "nist.gov", total_controls: 106 },
      { id: 2, code: "nist-800-53-r5", name: "NIST SP 800-53 Rev.5", version: "5.1.1", publisher: "nist.gov", total_controls: 1189 },
      { id: 3, code: "iso-27001-2022", name: "ISO/IEC 27001:2022 信息安全管理体系", version: "2022", publisher: "iso.org", total_controls: 93 },
    ];
  }

  if (url === "/api/controls") {
    return [
      { id: 1, code: "AC-1", title: "访问控制策略与规程", category: "Access Control", status: "implemented", description: "建立、分发并审查组织范围内的访问控制策略与配套实施流程。" },
      { id: 2, code: "IA-2", title: "身份识别与鉴别 (组织级)", category: "Identification & Auth", status: "in_progress", description: "针对所有内部网络和特权账户访问强制要求启用抗钓鱼多因素认证 (MFA)。" },
      { id: 3, code: "SC-7", title: "边界防护与微隔离机制", category: "System & Comm", status: "implemented", description: "在网络内部关键业务系统间实施零信任微隔离和深层数据包检测。" },
      { id: 4, code: "SI-4", title: "信息系统监控与入侵检测", category: "System Integrity", status: "implemented", description: "全天候 24/7 收集生产集群系统日志、审计跟踪并接入 SIEM 告警中心。" },
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
      { id: 1, title: "2026 Q3 堡垒机审计记录与跳板机访问回放", status: "valid", control_code: "AC-1", expires_at: "2026-12-31" },
      { id: 2, title: "生产数据库 SSL 泛域名证书轮换工单", status: "expired", control_code: "SC-7", expires_at: "2026-08-15" },
      { id: 3, title: "第三方渗透测试评估总结报告 (2026)", status: "valid", control_code: "SI-4", expires_at: "2027-03-01" },
    ];
  }

  if (url === "/api/proposals") {
    return [
      { id: 101, kind: "mapping", source_text: "第 4.2 条：所有进入生产机房的人员须经双人复核并留痕", target_framework: "NIST CSF 2.0 PR.AC-1", confidence: 0.94, status: "pending" },
      { id: 102, kind: "extraction", source_text: "第 7.1 条：静态数据与传输数据均应采用 AES-256 或同等级别加密", target_framework: "ISO 27001 A.10.1", confidence: 0.89, status: "pending" },
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
