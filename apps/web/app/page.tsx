"use client";

import { ChangeEvent, FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:18000";

type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

type KnowledgeDocument = {
  id: string;
  name: string;
  status: "uploaded" | "processing" | "ready" | "failed" | "revoked";
  parser_name: string | null;
  error_code: string | null;
  domain: string;
  purpose: string;
  owner_scope: "personal" | "organization";
  classification: string;
};
type ChatUpload = {
  id: string; conversation_id: string; document_id: string; name: string;
  status: string; domain: string; purpose: string; created_at: string; local_size?: number;
};

type Approval = {
  approval_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
};

type Citation = {
  citation_id: string;
  document_id: string;
  title: string;
  locator: Record<string, unknown>;
};

type SourcePreviewItem = Citation & {
  content: string;
  source_uri: string;
  is_target: boolean;
};

type IntegrationConnection = {
  id: string;
  provider: "jira" | "slack";
  name: string;
  endpoint_url: string;
  scope: "organization" | "personal";
  status: "active" | "disabled" | "error" | "expired" | "revoked";
  organization_id: string;
};
type ConnectionGrant = { id: string; subject_type: string; subject_id: string; tool_name: string; permission: string };

type AgentCard = { code: string; name: string; category: string; capabilities: string[]; allowed_actions: string[] };
type AgentAssignment = { id: string; agent_code: string; target_type: string; target_id: string; actions: string[]; effect: string; classification_ceiling: string; active: boolean };
type CompanyCatalogItem = { code: string; name: string; description: string; category: string; selected_version: string; versions: string[]; installed: boolean; enabled: boolean };
type RunPlanPreview = { work_class: "fast" | "standard" | "background"; step_count: number; agent_codes: string[] };
type SettingsSection = { code: string; label: string };
type CompanyUnit = { id: string; kind: "department" | "team" | "project"; code: string; name: string; department_id: string | null; manager_user_id: string | null; classification_ceiling: string | null; status: string };
type CompanyPerson = { user_id: string; display_name: string; email: string | null; status: string; classification_clearance: string; role_codes: string[] };
type CompanyRoleHistory = { id: string; role_code: string; valid_from: string; revoked_at: string | null };
type CompanyAccessPreview = { user_id: string; organization_id: string; policy_version: string; evaluated_at: string; scope: string; agents: { code: string; name: string; category: string; allowed_actions: string[]; reason_code: string }[]; proposed_role: string | null; role_operation: "add" | "remove" | null; proposed_scope_kind: "department" | "team" | "project" | null; proposed_scope_id: string | null; scope_operation: "add" | "remove" | null; proposed_agents: { code: string; name: string; category: string; allowed_actions: string[]; reason_code: string }[]; gained_agents: string[]; lost_agents: string[]; action_changes: { code: string; name: string; gained_actions: string[]; lost_actions: string[] }[]; tool_grants: { provider: "jira" | "slack"; connection_name: string; tool_name: string; permission: "read" | "draft" | "execute" | "administer" }[]; tools_truncated: boolean };
type CompanyInvitation = { id: string; department_id: string; department_name: string; status: string; expires_at: string };
type InvitationPreview = { organization_name: string; department_id: string; department_name: string; expires_at: string };
type AIProfile = { name: string; kind: "llm" | "embedding"; provider: string; model: string; endpoint: string; status: string; version: number; has_secret_reference: boolean; capabilities: string[]; routing_priority: number };
type AIHealth = { healthy: boolean; latency_ms: number; models: string[]; error_code: string | null };
type ArtifactPolicy = {
  organization_id: string;
  brand_name: string;
  footer_text: string;
  require_classification_mark: boolean;
  retention_days: number;
  monthly_artifact_limit: number;
};
type ArtifactTemplate = { id: string; name: string; artifact_type: string; output_format: string; body: string; active: boolean };
type ArtifactUsage = { artifact_count: number; stored_bytes: number; input_units: number; output_units: number; estimated_cost_micros: number };
type ArtifactItem = { id: string; name: string; artifact_type: string; status: string; classification: string; project_id: string | null; current_version: number; updated_at: string };
type ChatArtifact = { id: string; name: string; artifact_type: string; status: string; version: number; download_url: string };
type ArtifactAction = { id: string; status: string; provider: string | null; external_id: string | null; error_code: string | null; attempt_count: number; max_attempts: number };
type ActionMapping = { id: string; action: string; destination_type: string; tool_name: string; destination_field: string; content_field: string; active: boolean };
type BackgroundJob = {
  id: string; kind: string; risk: string; status: string; priority: number;
  progress_stage: string; completed_units: number; total_units: number | null;
  cancel_requested: boolean; created_at: string; updated_at: string;
};
type Locale = "ar" | "en";
type Theme = "light" | "dark";
type CenterNotification = { id: string; kind: "job" | "artifact" | "integration"; title: string; detail: string; updatedAt: string | null; target: "jobs" | "artifacts" | "integrations" };

const copy = (locale: Locale, arabic: string, english: string) => locale === "ar" ? arabic : english;

const suggestions = [
  { icon: "◫", title: "حالة المشروع", titleEn: "Project status", prompt: "اعرض لي حالة المشروع الحالية وأهم نقاط المتابعة", promptEn: "Summarize current project status and key follow-ups." },
  { icon: "↗", title: "البنود المتأخرة", titleEn: "Overdue items", prompt: "ما هي البنود المتأخرة في المشروع؟", promptEn: "Which items are overdue in the project?" },
  { icon: "✓", title: "مهمة متابعة", titleEn: "Follow-up task", prompt: "أنشئ مهمة متابعة لمراجعة فلو الموافقات", promptEn: "Create a follow-up task to review the approval flow." },
  { icon: "▤", title: "عرض تقديمي", titleEn: "Presentation", prompt: "اعمل عرض PPTX عن خطوات المشروع وحالته الحالية", promptEn: "Create a PPTX about the project steps and current status." },
] as const;

function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number, count: number) {
  const rtl = getComputedStyle(event.currentTarget).direction === "rtl";
  let nextIndex: number | null = null;
  if (event.key === "ArrowRight") nextIndex = (index + (rtl ? -1 : 1) + count) % count;
  else if (event.key === "ArrowLeft") nextIndex = (index + (rtl ? 1 : -1) + count) % count;
  else if (event.key === "Home") nextIndex = 0;
  else if (event.key === "End") nextIndex = count - 1;
  if (nextIndex === null) return;
  const tabs = event.currentTarget.closest('[role="tablist"]')?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
  const nextTab = tabs?.[nextIndex];
  if (!nextTab) return;
  event.preventDefault();
  nextTab.focus();
  nextTab.click();
}

export default function HomePage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [uploadDomain, setUploadDomain] = useState("project");
  const [uploadPurpose, setUploadPurpose] = useState("authoritative");
  const [selectedUpload, setSelectedUpload] = useState<File | null>(null);
  const [uploadOrigin, setUploadOrigin] = useState<"chat" | "knowledge">("chat");
  const [knowledgeView, setKnowledgeView] = useState<"personal" | "organization">("personal");
  const [confirmCompanyUpload, setConfirmCompanyUpload] = useState(false);
  const [canManageCompany, setCanManageCompany] = useState(false);
  const [chatUploads, setChatUploads] = useState<ChatUpload[]>([]);
  const [uploadingChatFile, setUploadingChatFile] = useState<string | null>(null);
  const [documentDomainFilter, setDocumentDomainFilter] = useState("all");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [runStep, setRunStep] = useState<string | null>(null);
  const [runPlan, setRunPlan] = useState<RunPlanPreview | null>(null);
  const [streamedAnswer, setStreamedAnswer] = useState("");
  const [approval, setApproval] = useState<Approval | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [sourcePreview, setSourcePreview] = useState<SourcePreviewItem[] | null>(null);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);
  const [integrationsOpen, setIntegrationsOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [personalSettingsOpen, setPersonalSettingsOpen] = useState(false);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [locale, setLocale] = useState<Locale>("ar");
  const [theme, setTheme] = useState<Theme>("light");
  const [profileName, setProfileName] = useState("Ahmed");
  const [profilePhoto, setProfilePhoto] = useState("");
  const [readNotificationIds, setReadNotificationIds] = useState<string[]>([]);
  const [preferencesLoaded, setPreferencesLoaded] = useState(false);
  const [jobsOpen, setJobsOpen] = useState(false);
  const [artifactsOpen, setArtifactsOpen] = useState(false);
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [chatArtifact, setChatArtifact] = useState<ChatArtifact | null>(null);
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [agents, setAgents] = useState<AgentCard[]>([]);
  const [aiProfiles, setAiProfiles] = useState<AIProfile[]>([]);
  const [settingsSections, setSettingsSections] = useState<SettingsSection[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [invitationToken, setInvitationToken] = useState("");
  const [invitationPreview, setInvitationPreview] = useState<InvitationPreview | null>(null);
  const [invitationMessage, setInvitationMessage] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const profilePhotoInput = useRef<HTMLInputElement>(null);
  const endOfMessages = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const preferences = JSON.parse(localStorage.getItem("tactiqo.ui.preferences") ?? "{}") as {
        locale?: Locale; theme?: Theme; profileName?: string; profilePhoto?: string; readNotificationIds?: string[];
      };
      if (preferences.locale === "ar" || preferences.locale === "en") setLocale(preferences.locale);
      if (preferences.theme === "light" || preferences.theme === "dark") setTheme(preferences.theme);
      if (typeof preferences.profileName === "string" && preferences.profileName.trim()) setProfileName(preferences.profileName);
      if (typeof preferences.profilePhoto === "string") setProfilePhoto(preferences.profilePhoto);
      if (Array.isArray(preferences.readNotificationIds)) setReadNotificationIds(preferences.readNotificationIds.filter((id): id is string => typeof id === "string").slice(-300));
    } catch { /* Ignore malformed, browser-local preference data. */ }
    setPreferencesLoaded(true);
  }, []);

  useEffect(() => {
    if (!preferencesLoaded) return;
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("tactiqo.ui.preferences", JSON.stringify({ locale, theme, profileName, profilePhoto, readNotificationIds: readNotificationIds.slice(-300) }));
    } catch { setNotice(copy(locale, "تعذر حفظ التفضيلات محليًا في هذا المتصفح.", "Could not save preferences in this browser.")); }
  }, [locale, theme, profileName, profilePhoto, readNotificationIds, preferencesLoaded]);

  const request = useCallback(async <T,>(path: string, init?: RequestInit): Promise<T> => {
    const response = await fetch(`${API_BASE_URL}${path}`, init);
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `Request failed (${response.status})`);
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }, []);

  const refreshConversations = useCallback(async () => {
    const items = await request<Conversation[]>("/api/v1/conversations");
    setConversations(items);
  }, [request]);

  const refreshDocuments = useCallback(async () => {
    const [personal, company] = await Promise.all([
      request<KnowledgeDocument[]>("/api/v1/knowledge/documents?owner_scope=personal"),
      request<KnowledgeDocument[]>("/api/v1/knowledge/documents?owner_scope=organization"),
    ]);
    setDocuments([...personal, ...company]);
  }, [request]);

  const refreshConnections = useCallback(async () => {
    const items = await request<IntegrationConnection[]>("/api/v1/integrations/connections");
    setConnections(items);
  }, [request]);

  const refreshSettings = useCallback(async () => {
    const [agentItems, sections] = await Promise.all([
      request<AgentCard[]>("/api/v1/agents"),
      request<SettingsSection[]>("/api/v1/company/settings/navigation"),
    ]);
    setAgents(agentItems);
    setSettingsSections(sections);
    setCanManageCompany(sections.some((item) => item.code === "structure"));
    try {
      const profiles = await request<AIProfile[]>("/api/v1/ai/profiles");
      setAiProfiles(profiles);
    } catch {
      setAiProfiles([]);
    }
  }, [request]);

  const refreshJobs = useCallback(async () => {
    setJobs(await request<BackgroundJob[]>("/api/v1/jobs"));
  }, [request]);

  const refreshArtifacts = useCallback(async () => {
    setArtifacts(await request<ArtifactItem[]>("/api/v1/artifacts"));
  }, [request]);

  const openSourcePreview = async (citation: Citation) => {
    const ordinal = Number(citation.citation_id.split(":").at(-1));
    if (!citation.document_id || !Number.isInteger(ordinal)) {
      setNotice("تعذر تحديد موضع المصدر.");
      return;
    }
    try {
      setSourcePreview(await request<SourcePreviewItem[]>(
        `/api/v1/knowledge/documents/${citation.document_id}/preview?chunk_ordinal=${ordinal}&radius=1`,
      ));
    } catch {
      setNotice("المصدر غير متاح لك أو تغيرت صلاحياته.");
    }
  };

  useEffect(() => {
    void Promise.all([refreshConversations(), refreshDocuments(), refreshConnections(), refreshSettings(), refreshJobs(), refreshArtifacts()]).catch(() => {
      setNotice("تعذر الاتصال بالخادم. تأكد أن خدمات Tactiqo تعمل.");
    });
  }, [refreshArtifacts, refreshConnections, refreshConversations, refreshDocuments, refreshJobs, refreshSettings]);

  useEffect(() => {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const token = fragment.get("invite");
    if (!token) return;
    history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    setInvitationToken(token);
    void request<InvitationPreview>("/api/v1/auth/invitations/preview", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    }).then(setInvitationPreview).catch(() => setInvitationMessage("الرابط غير صالح أو انتهت صلاحيته أو تم إلغاؤه."));
  }, [request]);

  useEffect(() => {
    if (!jobsOpen) return;
    void refreshJobs();
    const timer = window.setInterval(() => void refreshJobs(), 3000);
    return () => window.clearInterval(timer);
  }, [jobsOpen, refreshJobs]);

  useEffect(() => {
    if (!notificationsOpen) return;
    const timer = window.setInterval(() => {
      void Promise.all([refreshJobs(), refreshArtifacts(), refreshConnections()]).catch(() => undefined);
    }, 15000);
    return () => window.clearInterval(timer);
  }, [notificationsOpen, refreshArtifacts, refreshConnections, refreshJobs]);

  useEffect(() => {
    endOfMessages.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streamedAnswer, approval, runStep]);

  const joinInvitation = async () => {
    try {
      const result = await request<{ authorization_url: string }>("/api/v1/auth/invitations/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: invitationToken }),
      });
      window.location.assign(result.authorization_url);
    } catch {
      setInvitationMessage("تعذر بدء تسجيل الدخول. قد يحتاج مسؤول النظام إلى إعداد مزود OIDC.");
    }
  };

  const openConversation = async (id: string) => {
    if (busy) return;
    setConversationId(id);
    const [messageItems, attachmentItems] = await Promise.all([
      request<Message[]>(`/api/v1/conversations/${id}/messages`),
      request<ChatUpload[]>(`/api/v1/conversations/${id}/attachments`),
    ]);
    setMessages(messageItems);
    setChatUploads(attachmentItems);
    setStreamedAnswer("");
    setApproval(null);
    setCitations([]);
    setChatUploads([]);
    setChatArtifact(null);
    setSidebarOpen(false);
  };

  const newChat = () => {
    if (busy) return;
    setConversationId(null);
    setMessages([]);
    setStreamedAnswer("");
    setApproval(null);
    setCitations([]);
    setChatArtifact(null);
    setInput("");
    setSidebarOpen(false);
  };

  const ensureConversation = async (firstMessage: string): Promise<string> => {
    if (conversationId) return conversationId;
    const conversation = await request<Conversation>("/api/v1/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: firstMessage.trim().slice(0, 52) }),
    });
    setConversationId(conversation.id);
    setConversations((current) => [conversation, ...current]);
    return conversation.id;
  };

  const watchRun = (id: string, chatId: string) => {
    const stream = new EventSource(`${API_BASE_URL}/api/v1/runs/${id}/events`);
    stream.addEventListener("run.step", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as { step: string; work_class?: RunPlanPreview["work_class"]; step_count?: number; agent_codes?: string[] };
      setRunStep(data.step);
      if (data.step === "plan_compiled" && data.work_class && data.step_count && data.agent_codes) {
        setRunPlan({ work_class: data.work_class, step_count: data.step_count, agent_codes: data.agent_codes });
      }
    });
    stream.addEventListener("retrieval.completed", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as { citations: Citation[] };
      setCitations(data.citations ?? []);
      setRunStep("retrieval");
    });
    stream.addEventListener("tool.call", () => setRunStep("tool"));
    stream.addEventListener("artifact.created", (event) => {
      const item = JSON.parse((event as MessageEvent).data) as ChatArtifact;
      setChatArtifact(item);
      setRunStep("artifact_creation");
      void refreshArtifacts();
    });
    stream.addEventListener("approval.required", (event) => {
      setApproval(JSON.parse((event as MessageEvent).data) as Approval);
      setRunStep("approval");
    });
    stream.addEventListener("message.delta", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as { delta: string };
      setStreamedAnswer((current) => current + data.delta);
      setRunStep("responding");
    });
    stream.addEventListener("message.completed", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as { content: string };
      setStreamedAnswer(data.content);
    });
    const finish = async () => {
      stream.close();
      setBusy(false);
      setRunId(null);
      setRunStep(null);
      setRunPlan(null);
      setApproval(null);
      setMessages(await request<Message[]>(`/api/v1/conversations/${chatId}/messages`));
      setStreamedAnswer("");
      await refreshConversations();
    };
    stream.addEventListener("run.completed", () => void finish());
    stream.addEventListener("run.cancelled", () => void finish());
    stream.addEventListener("run.failed", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as { message?: string };
      setNotice(data.message ?? "تعذر إكمال الطلب بأمان.");
      void finish();
    });
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const content = input.trim();
    if (!content || busy) return;
    setInput("");
    setNotice(null);
    setBusy(true);
    setStreamedAnswer("");
    setRunPlan(null);
    setApproval(null);
    setCitations([]);
    setChatArtifact(null);
    const optimistic: Message = {
      id: `local-${Date.now()}`,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, optimistic]);
    try {
      const id = await ensureConversation(content);
      const run = await request<{ id: string }>(`/api/v1/conversations/${id}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      setRunId(run.id);
      setRunStep("queued");
      watchRun(run.id, id);
    } catch {
      setBusy(false);
      setNotice("لم يتم إرسال الرسالة. حاول مرة أخرى.");
    }
  };

  const decide = async (decision: "approved" | "rejected") => {
    if (!approval) return;
    const approvalId = approval.approval_id;
    setApproval(null);
    setRunStep(decision === "approved" ? "tool" : "responding");
    try {
      await request(`/api/v1/approvals/${approvalId}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      });
    } catch {
      setNotice("تعذر تسجيل قرار الموافقة.");
    }
  };

  const cancel = async () => {
    if (!runId) return;
    await request(`/api/v1/runs/${runId}/cancel`, { method: "POST" });
    setRunStep("cancelling");
  };

  const chooseUpload = (origin: "chat" | "knowledge") => {
    setUploadOrigin(origin);
    setConfirmCompanyUpload(false);
    fileInput.current?.click();
  };

  const selectUpload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setSelectedUpload(file);
  };

  const upload = async () => {
    const file = selectedUpload;
    if (!file) return;
    const origin = uploadOrigin;
    setSelectedUpload(null);
    if (origin === "chat") setUploadingChatFile(file.name);
    setNotice(`جاري رفع ${file.name}…`);
    const form = new FormData();
    form.append("file", file);
    form.append("domain", uploadDomain);
    form.append("purpose", uploadPurpose);
    form.append("owner_scope", uploadOrigin === "chat" ? "personal" : knowledgeView);
    try {
      const chatId = origin === "chat" ? await ensureConversation(file.name) : null;
      if (chatId) form.append("conversation_id", chatId);
      const document = await request<KnowledgeDocument>("/api/v1/knowledge/documents", { method: "POST", body: form });
      if (origin === "chat") {
        const attachments = await request<ChatUpload[]>(`/api/v1/conversations/${chatId}/attachments`);
        setChatUploads(attachments.map((item) => item.document_id === document.id ? { ...item, local_size: file.size } : item));
      }
      setNotice("تم رفع المستند، وبدأت معالجته وإضافته للمعرفة.");
      setKnowledgeOpen(true);
      await refreshDocuments();
      window.setTimeout(() => void refreshDocuments(), 1800);
    } catch {
      setNotice("تعذر رفع المستند. الحد المحلي الحالي 100MB.");
    } finally {
      setUploadingChatFile(null);
    }
  };

  const revokeDocument = async (document: KnowledgeDocument) => {
    const confirmation = window.prompt(
      `لإلغاء المصدر وحذف فهرسه، اكتب اسم الملف كاملًا:\n${document.name}`,
    );
    if (confirmation === null) return;
    try {
      await request(`/api/v1/knowledge/documents/${document.id}/revoke`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmation_name: confirmation }),
      });
      setNotice("تم إلغاء المصدر وحذف بيانات البحث المشتقة منه.");
      await refreshDocuments();
    } catch {
      setNotice("لم يتم الإلغاء. تأكد من كتابة اسم الملف ومن صلاحياتك.");
    }
  };

  const promoteDocument = async (document: KnowledgeDocument) => {
    const confirmation = window.prompt(
      `تحويل الملف إلى معرفة الشركة سيجعله متاحًا لموظفي المؤسسة المسموح لهم بدرجة ${document.classification}. اكتب الاسم للتأكيد:\n${document.name}`,
    );
    if (confirmation === null) return;
    try {
      await request(`/api/v1/knowledge/documents/${document.id}/promote`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmation_name: confirmation }),
      });
      setNotice("تم نقل المصدر إلى معرفة الشركة وتحديث صلاحيات البحث.");
      await refreshDocuments();
    } catch { setNotice("تعذر نقل المصدر. تحقق من الاسم وصلاحيات الإدارة."); }
  };

  const stepLabel: Record<string, string> = {
    queued: "جاري بدء الوكيل",
    guardrails: "فحص الحماية",
    memory: "تجهيز سياق المحادثة",
    classification: "تحديد أسرع مسار للطلب",
    retrieval: "البحث في المعرفة",
    planning: "تخطيط الخطوات",
    artifact_creation: "إنشاء الملف وحفظه كمسودة",
    tool: "تشغيل الأداة",
    approval: "بانتظار موافقتك",
    responding: "صياغة الإجابة",
    cancelling: "جاري الإلغاء",
  };

  const notifications: CenterNotification[] = [
    ...jobs.filter((job) => ["waiting_approval", "failed", "dead_letter"].includes(job.status)).map((job) => ({
      id: `job:${job.id}:${job.status}:${job.updated_at}`, kind: "job" as const,
      title: job.status === "waiting_approval" ? "مهمة تنتظر الموافقة" : job.status === "dead_letter" ? "مهمة تحتاج تدخلًا" : "تعذر تنفيذ مهمة",
      detail: `${jobKindLabel[job.kind] ?? job.kind} · ${jobStatusLabel[job.status] ?? job.status}`,
      updatedAt: job.updated_at, target: "jobs" as const,
    })),
    ...artifacts.filter((artifact) => artifact.status === "in_review").map((artifact) => ({
      id: `artifact:${artifact.id}:${artifact.status}:${artifact.updated_at}`, kind: "artifact" as const,
      title: "مخرج ينتظر المراجعة", detail: artifact.name, updatedAt: artifact.updated_at, target: "artifacts" as const,
    })),
    ...connections.filter((connection) => ["error", "expired"].includes(connection.status)).map((connection) => ({
      id: `integration:${connection.id}:${connection.status}`, kind: "integration" as const,
      title: connection.status === "expired" ? "انتهت صلاحية اتصال" : "تعطل اتصال أداة",
      detail: `${connection.provider === "jira" ? "Jira" : "Slack"} · ${connection.name}`,
      updatedAt: null, target: "integrations" as const,
    })),
  ].sort((left, right) => new Date(right.updatedAt ?? 0).getTime() - new Date(left.updatedAt ?? 0).getTime());
  const unreadNotifications = notifications.filter((item) => !readNotificationIds.includes(item.id));

  const openNotification = (item: CenterNotification) => {
    setReadNotificationIds((current) => current.includes(item.id) ? current : [...current, item.id].slice(-300));
    setNotificationsOpen(false);
    if (item.target === "jobs") { setJobsOpen(true); void refreshJobs(); }
    if (item.target === "artifacts") { setArtifactsOpen(true); void refreshArtifacts(); }
    if (item.target === "integrations") { setIntegrationsOpen(true); void refreshConnections(); }
  };

  const changeProfilePhoto = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!/^image\/(jpeg|png|webp|gif|avif)$/.test(file.type) || file.size > 1024 * 1024) {
      setNotice(copy(locale, "اختر صورة أقل من 1 ميجابايت.", "Choose an image smaller than 1 MB."));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setProfilePhoto(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => setNotice(copy(locale, "تعذر قراءة الصورة.", "Could not read the image."));
    reader.readAsDataURL(file);
  };

  return (
    <main className="app-shell">
      {invitationToken && <div className="invitation-overlay" role="dialog" aria-modal="true" aria-labelledby="invitation-title"><section><h1 id="invitation-title">الانضمام إلى مؤسسة</h1>{invitationPreview ? <><p>تمت دعوتك إلى <strong>{invitationPreview.organization_name}</strong>.</p><p>القسم: <strong>{invitationPreview.department_name}</strong></p><p className="settings-note">ينتهي الرابط {new Date(invitationPreview.expires_at).toLocaleString("ar-EG")} ويُستخدم مرة واحدة.</p><button className="settings-action" onClick={() => void joinInvitation()}>تسجيل الدخول والانضمام</button></> : <p role={invitationMessage ? "alert" : "status"}>{invitationMessage || "جارٍ التحقق من الرابط…"}</p>}<button className="danger" onClick={() => { setInvitationToken(""); setInvitationPreview(null); setInvitationMessage(""); }}>إغلاق</button></section></div>}
      {personalSettingsOpen && <div className="settings-modal-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPersonalSettingsOpen(false); }}><section className="settings-modal personal-settings-modal" role="dialog" aria-modal="true" aria-labelledby="personal-settings-title" dir={locale === "ar" ? "rtl" : "ltr"}>
        <header><div><small>{copy(locale, "تفضيلات هذا المتصفح", "THIS BROWSER ONLY")}</small><h2 id="personal-settings-title">{copy(locale, "الإعدادات الشخصية", "Personal settings")}</h2></div><button type="button" onClick={() => setPersonalSettingsOpen(false)} aria-label={copy(locale, "إغلاق", "Close")}>×</button></header>
        <div className="personal-settings-content">
          <div className="profile-editor"><span className={`avatar profile-large ${profilePhoto ? "photo" : ""}`} style={profilePhoto ? { backgroundImage: `url(${profilePhoto})` } : undefined}>{!profilePhoto && (profileName.trim().slice(0, 1) || "A")}</span><div><strong>{copy(locale, "الملف الشخصي", "Profile")}</strong><small>{copy(locale, "الاسم والصورة محفوظان محليًا على هذا الجهاز فقط.", "Name and photo are stored locally on this device only.")}</small></div></div>
          <label>{copy(locale, "الاسم الظاهر", "Display name")}<input value={profileName} maxLength={80} onChange={(event) => setProfileName(event.target.value)} /></label>
          <input ref={profilePhotoInput} type="file" accept="image/*" hidden onChange={changeProfilePhoto} />
          <div className="settings-row"><button type="button" className="settings-action secondary" onClick={() => profilePhotoInput.current?.click()}>{copy(locale, "تغيير الصورة", "Change photo")}</button>{profilePhoto && <button type="button" className="settings-action secondary" onClick={() => setProfilePhoto("")}>{copy(locale, "إزالة الصورة", "Remove photo")}</button>}</div>
          <label>{copy(locale, "لغة الواجهة", "Interface language")}<select value={locale} onChange={(event) => setLocale(event.target.value as Locale)}><option value="ar">العربية</option><option value="en">English</option></select></label>
          <label>{copy(locale, "المظهر", "Appearance")}<select value={theme} onChange={(event) => setTheme(event.target.value as Theme)}><option value="light">{copy(locale, "فاتح", "Light")}</option><option value="dark">{copy(locale, "داكن", "Dark")}</option></select></label>
          <p className="settings-note">{copy(locale, "هذه التفضيلات محلية لهذا المتصفح وليست جزءًا من ملف حساب مركزي. إعدادات الشركة تظهر منفصلة في قائمة الحساب، وفقط إذا سمح الخادم بذلك.", "These preferences are local to this browser, not a central account profile. Company settings are separate in the account menu and appear only when allowed by the server.")}</p>
        </div>
      </section></div>}
      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark">T</div>
          <div><strong>Tactiqo</strong><span>AI Operations</span></div>
          <button className="icon-button mobile-only" onClick={() => setSidebarOpen(false)} aria-label={copy(locale, "إغلاق القائمة", "Close menu")}>×</button>
        </div>
        <button className="new-chat" onClick={newChat}><span>＋</span> {copy(locale, "محادثة جديدة", "New chat")}</button>
        <p className="sidebar-label">{copy(locale, "المحادثات", "Chats")}</p>
        <nav className="conversation-list" aria-label={copy(locale, "المحادثات السابقة", "Recent chats")}>
          {conversations.length === 0 && <span className="empty-list">{copy(locale, "لا توجد محادثات بعد", "No chats yet")}</span>}
          {conversations.map((conversation) => (
            <button
              className={conversation.id === conversationId ? "conversation active" : "conversation"}
              key={conversation.id}
              onClick={() => void openConversation(conversation.id)}
            >
              <span className="chat-icon">⌁</span><span>{conversation.title}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="security-row"><span>◈</span><div><strong>{copy(locale, "وضع مؤسسي آمن", "Governed workspace")}</strong><small>{copy(locale, "الموافقات والتدقيق مفعّلان", "Approvals and audit enabled")}</small></div></div>
          <div className="profile-wrap">
            <div className="profile"><span className={`avatar small ${profilePhoto ? "photo" : ""}`} style={profilePhoto ? { backgroundImage: `url(${profilePhoto})` } : undefined}>{!profilePhoto && (profileName.trim().slice(0, 1) || "A")}</span><div><strong>{profileName}</strong><small>{copy(locale, "مساحة العمل المحلية", "Local workspace")}</small></div><button type="button" className="profile-menu-button" aria-label={copy(locale, "فتح قائمة الحساب والإعدادات", "Open account and settings menu")} aria-expanded={profileMenuOpen} onClick={() => setProfileMenuOpen((value) => !value)}>•••</button></div>
            {profileMenuOpen && <div className="profile-menu" role="menu">
              <button role="menuitem" onClick={() => { setProfileMenuOpen(false); setPersonalSettingsOpen(true); }}>{copy(locale, "الإعدادات الشخصية", "Personal settings")}</button>
              {settingsSections.length > 0 && <button role="menuitem" onClick={() => { setProfileMenuOpen(false); setSettingsOpen(true); }}>{copy(locale, "إعدادات الشركة", "Company settings")}</button>}
            </div>}
          </div>
        </div>
      </aside>

      {sidebarOpen && <button className="scrim" onClick={() => setSidebarOpen(false)} aria-label="إغلاق القائمة" />}

      <section className="workspace">
        <header className="topbar">
          <button className="icon-button menu-button" onClick={() => setSidebarOpen(true)} aria-label={copy(locale, "فتح القائمة", "Open menu")}>☰</button>
          <div className="model-select">{aiProfiles.filter((item) => item.kind === "llm" && item.status === "enabled").sort((a, b) => a.routing_priority - b.routing_priority)[0]?.model ?? "Tactiqo Agent"} <span>●</span></div>
          <div className="top-actions">
            <span className="live-badge"><i /> {copy(locale, "النظام متصل", "System online")}</span>
            <button className="knowledge-button" aria-label={copy(locale, "الإشعارات", "Notifications")} aria-expanded={notificationsOpen} onClick={() => { setNotificationsOpen((value) => !value); void Promise.all([refreshJobs(), refreshArtifacts(), refreshConnections()]).catch(() => setNotice(copy(locale, "تعذر تحديث الإشعارات.", "Could not refresh notifications."))); }}>🔔<span>{copy(locale, "الإشعارات", "Notifications")}</span>{unreadNotifications.length > 0 && <i className="notification-count">{unreadNotifications.length > 99 ? "99+" : unreadNotifications.length}</i>}</button>
            <button className="knowledge-button" aria-label={copy(locale, "المعرفة", "Knowledge")} onClick={() => setKnowledgeOpen((value) => !value)}>▱ <span>{copy(locale, "المعرفة", "Knowledge")}</span></button>
            <button className="knowledge-button" aria-label={copy(locale, "التكاملات", "Integrations")} onClick={() => setIntegrationsOpen((value) => !value)}>⌘ <span>{copy(locale, "التكاملات", "Integrations")}</span></button>
            <button className="knowledge-button" aria-label={copy(locale, "المهام", "Jobs")} onClick={() => setJobsOpen((value) => !value)}>◴ <span>{copy(locale, "المهام", "Jobs")}</span></button>
            <button className="knowledge-button" aria-label={copy(locale, "المخرجات", "Outputs")} onClick={() => setArtifactsOpen((value) => !value)}>▤ <span>{copy(locale, "المخرجات", "Outputs")}</span></button>
          </div>
          {notificationsOpen && <section className="notification-center" aria-label={copy(locale, "مركز الإشعارات", "Notification center")}>
            <div className="notification-heading"><div><strong>{copy(locale, "الإشعارات", "Notifications")}</strong><small>{copy(locale, `${unreadNotifications.length} غير مقروء`, `${unreadNotifications.length} unread`)}</small></div><div><button type="button" onClick={() => setReadNotificationIds(notifications.map((item) => item.id))} disabled={unreadNotifications.length === 0}>{copy(locale, "تحديد الكل كمقروء", "Mark all read")}</button><button type="button" onClick={() => setNotificationsOpen(false)} aria-label={copy(locale, "إغلاق", "Close")}>×</button></div></div>
            {notifications.length === 0 ? <p className="notification-empty">{copy(locale, "لا توجد إشعارات حاليًا.", "You're all caught up.")}</p> : <div className="notification-list">{notifications.map((item) => <button key={item.id} className={`notification-item ${readNotificationIds.includes(item.id) ? "read" : "unread"}`} onClick={() => openNotification(item)}><i className={`notification-icon ${item.kind}`} /><span><strong>{copy(locale, item.title, ({ "مهمة تنتظر الموافقة": "A job needs approval", "مهمة تحتاج تدخلًا": "A job needs attention", "تعذر تنفيذ مهمة": "A job failed", "مخرج ينتظر المراجعة": "An output needs review", "انتهت صلاحية اتصال": "Integration authorization expired", "تعطل اتصال أداة": "An integration failed" } as Record<string, string>)[item.title] ?? item.title)}</strong><small>{item.detail}</small>{item.updatedAt && <time>{new Date(item.updatedAt).toLocaleString(locale === "ar" ? "ar-EG" : "en-US")}</time>}</span></button>)}</div>}
          </section>}
        </header>

        <div className="chat-scroll">
          {messages.length === 0 && chatUploads.length === 0 && !uploadingChatFile && !busy ? (
            <section className="welcome">
              <div className="welcome-mark">T</div>
            <h1>{copy(locale, "كيف أقدر أساعدك اليوم؟", "How can I help today?")}</h1>
            <p>{copy(locale, "اسأل عن مشاريعك، حلّل مستندًا، أو شغّل أداة. كل إجراء مؤثر يحتاج موافقتك أولًا.", "Ask about your projects, analyze a document, or use a tool. Actions with impact require your approval first.")}</p>
              <div className="suggestion-grid">
                {suggestions.map((item) => (
                  <button key={item.title} onClick={() => setInput(locale === "ar" ? item.prompt : item.promptEn)}>
                    <span>{item.icon}</span><strong>{copy(locale, item.title, item.titleEn)}</strong><small>{copy(locale, item.prompt, item.promptEn)}</small>
                  </button>
                ))}
              </div>
            </section>
          ) : (
            <div className="message-thread">
              {messages.map((message) => <ChatMessage key={message.id} message={message} />)}
              {chatUploads.map((document) => (
                <article className="message user-message" key={`upload-${document.id}`}>
                  <span className="avatar user">أ</span>
                  <div className="message-body chat-upload-card">
                    <strong>{document.name}</strong>
                    <span>{document.local_size ? `${(document.local_size / 1024 / 1024).toFixed(2)} MB · ` : ""}{document.domain} · {document.purpose}</span>
                    <small>تم الرفع للمعرفة · {documentStatus(document)}</small>
                  </div>
                </article>
              ))}
              {uploadingChatFile && <article className="message user-message" aria-live="polite"><span className="avatar user">أ</span><div className="message-body chat-upload-card"><strong>{uploadingChatFile}</strong><small>جاري الرفع وإضافة الملف إلى المحادثة…</small></div></article>}
              {(busy || streamedAnswer) && (
                <article className="message assistant-message">
                  <span className="avatar agent">T</span>
                  <div className="message-body">
              <strong className="message-name">Tactiqo</strong>
                    {runPlan && busy && <div className="run-plan-preview" role="status"><strong>{runPlan.work_class === "fast" ? "مسار سريع" : runPlan.work_class === "background" ? "مهمة خلفية" : "خطة تنفيذ"}</strong><span>{runPlan.step_count} خطوة · {runPlan.agent_codes.map((code) => agents.find((item) => item.code === code)?.name ?? "وكيل مخوّل").join("، ")}</span></div>}
                    {streamedAnswer ? <p>{streamedAnswer}</p> : <Thinking label={stepLabel[runStep ?? "queued"]} />}
                    {citations.length > 0 && (
                      <div className="citations">
                        <span>المصادر</span>
                        {citations.map((citation, index) => (
                          <button key={citation.citation_id} onClick={() => void openSourcePreview(citation)}>
                            [{index + 1}] {citation.title}
                          </button>
                        ))}
                      </div>
                    )}
                    {chatArtifact && (
                      <div className="chat-artifact">
                        <strong>{chatArtifact.name}</strong>
                        <small>{chatArtifact.artifact_type} · {chatArtifact.status} · v{chatArtifact.version}</small>
                        <a href={`${API_BASE_URL}${chatArtifact.download_url}`} download>تنزيل الملف</a>
                        <button onClick={() => setArtifactsOpen(true)}>فتح المخرجات والمراجعة</button>
                      </div>
                    )}
                    {approval && <ApprovalCard approval={approval} onDecide={decide} />}
                  </div>
                </article>
              )}
              <div ref={endOfMessages} />
            </div>
          )}
        </div>

        {sourcePreview && (
          <div className="source-preview" role="dialog" aria-modal="true" aria-label="معاينة المصدر">
            <button className="preview-scrim" onClick={() => setSourcePreview(null)} aria-label="إغلاق" />
            <section>
              <header>
                <div><small>{copy(locale, "مصدر موثّق", "Verified source")}</small><h2>{sourcePreview[0]?.title}</h2></div>
                <button onClick={() => setSourcePreview(null)} aria-label={copy(locale, "إغلاق", "Close")}>×</button>
              </header>
              <div className="preview-content">
                {sourcePreview.map((item) => (
                  <article key={item.citation_id} className={item.is_target ? "target" : ""}>
                    <small>{JSON.stringify(item.locator)}</small>
                    <p>{item.content}</p>
                  </article>
                ))}
              </div>
              <footer>{copy(locale, "تمت إعادة مراجعة صلاحياتك قبل عرض هذه المعاينة.", "Your access was rechecked before showing this preview.")}</footer>
            </section>
          </div>
        )}

        {selectedUpload && (
            <div className="upload-dialog" role="dialog" aria-modal="true" aria-label={copy(locale, "تصنيف الملف قبل الرفع", "Classify the file before upload")}>
            <button className="preview-scrim" onClick={() => setSelectedUpload(null)} aria-label="إلغاء" />
            <section>
              <header><div><small>{copy(locale, "ملف مختار", "Selected file")}</small><h2>{selectedUpload.name}</h2></div><button onClick={() => setSelectedUpload(null)}>×</button></header>
              <p>{copy(locale, "اختر التصنيف والاستخدام الآن. لن يبدأ الرفع قبل تأكيدك.", "Choose the file domain and purpose. Upload will not start until you confirm.")}</p>
              <label>{copy(locale, "مجال الملف", "File domain")}<select value={uploadDomain} onChange={(event) => setUploadDomain(event.target.value)}><option value="project">{copy(locale, "مشروع", "Project")}</option><option value="general">{copy(locale, "عام", "General")}</option><option value="hr">{copy(locale, "موارد بشرية", "Human resources")}</option><option value="finance">{copy(locale, "مالية", "Finance")}</option><option value="it">{copy(locale, "تقنية معلومات", "IT")}</option><option value="legal">{copy(locale, "قانوني", "Legal")}</option><option value="operations">{copy(locale, "عمليات", "Operations")}</option></select></label>
              <label>{copy(locale, "استخدام الملف", "File purpose")}<select value={uploadPurpose} onChange={(event) => setUploadPurpose(event.target.value)}><option value="authoritative">{copy(locale, "مرجع موثق", "Authoritative reference")}</option><option value="research">{copy(locale, "بحثي فقط", "Research only")}</option><option value="ignore">{copy(locale, "محفوظ ويُستبعد من RAG", "Stored but excluded from RAG")}</option></select></label>
              {uploadOrigin === "knowledge" && knowledgeView === "organization" && <label className="company-confirm"><input type="checkbox" checked={confirmCompanyUpload} onChange={(event) => setConfirmCompanyUpload(event.target.checked)} /> {copy(locale, "أفهم أن هذا الملف سيصبح مصدر معرفة للشركة، ويظهر فقط لمن تسمح له درجة السرية وصلاحيات المؤسسة.", "I understand this becomes company knowledge and is visible only according to classification and company permissions.")}</label>}
              <footer><button onClick={() => setSelectedUpload(null)}>{copy(locale, "إلغاء", "Cancel")}</button><button className="settings-action" disabled={uploadOrigin === "knowledge" && knowledgeView === "organization" && !confirmCompanyUpload} onClick={() => void upload()}>{copy(locale, "تأكيد وبدء الرفع", "Confirm and upload")}</button></footer>
            </section>
          </div>
        )}

        <div className="composer-zone">
          {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice(null)}>×</button></div>}
          {busy && <button className="cancel-run" onClick={() => void cancel()}>■ إيقاف التنفيذ</button>}
          <form className="composer" onSubmit={(event) => void submit(event)}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder={copy(locale, "اكتب رسالتك إلى Tactiqo…", "Message Tactiqo…")}
              rows={1}
              disabled={busy}
              aria-label={copy(locale, "رسالتك", "Your message")}
            />
            <div className="composer-actions">
              <input ref={fileInput} type="file" hidden onChange={selectUpload} accept=".pdf,.docx,.xlsx,.pptx,.csv,.txt,.md" />
              <button type="button" className="attach" onClick={() => chooseUpload("chat")} aria-label={copy(locale, "إرفاق مستند", "Attach a document")}>＋</button>
              <span className="composer-hint">{copy(locale, "يدعم المستندات والجداول حتى 100MB", "Documents and spreadsheets up to 100 MB")}</span>
              <button type="submit" className="send" disabled={!input.trim() || busy} aria-label={copy(locale, "إرسال", "Send")}>↑</button>
            </div>
          </form>
          <small className="disclaimer">{copy(locale, "قد يخطئ الذكاء الاصطناعي. راجع النتائج المهمة قبل الاعتماد عليها.", "AI can make mistakes. Review important results before relying on them.")}</small>
        </div>
      </section>

      <aside className={`knowledge-drawer ${knowledgeOpen ? "drawer-open" : ""}`} aria-label={copy(locale, "مصادر المعرفة", "Knowledge sources")} aria-hidden={!knowledgeOpen} inert={!knowledgeOpen}>
        <div className="drawer-header"><div><small>RAG KNOWLEDGE</small><h2>{copy(locale, "مصادر المعرفة", "Knowledge sources")}</h2></div><button onClick={() => setKnowledgeOpen(false)}>×</button></div>
        <p>{copy(locale, "المستندات الأصلية محفوظة في MinIO، والنص المنظم وحالته في PostgreSQL.", "Original files are stored in MinIO; parsed text and status are in PostgreSQL.")}</p>
        <div className="settings-tabs" role="tablist" aria-label={copy(locale, "نطاق المعرفة", "Knowledge scope")} aria-orientation="horizontal">
          <button id="knowledge-tab-personal" type="button" role="tab" aria-controls="knowledge-panel" aria-selected={knowledgeView === "personal"} tabIndex={knowledgeView === "personal" ? 0 : -1} className={knowledgeView === "personal" ? "active" : ""} onKeyDown={(event) => handleTabKeyDown(event, 0, 2)} onClick={() => setKnowledgeView("personal")}>{copy(locale, "معرفتي", "My knowledge")}</button>
          <button id="knowledge-tab-organization" type="button" role="tab" aria-controls="knowledge-panel" aria-selected={knowledgeView === "organization"} tabIndex={knowledgeView === "organization" ? 0 : -1} className={knowledgeView === "organization" ? "active" : ""} onKeyDown={(event) => handleTabKeyDown(event, 1, 2)} onClick={() => setKnowledgeView("organization")}>{copy(locale, "معرفة الشركة", "Company knowledge")}</button>
        </div>
        <div id="knowledge-panel" role="tabpanel" aria-labelledby={`knowledge-tab-${knowledgeView}`} tabIndex={0}>
        {(knowledgeView === "personal" || canManageCompany) && <button className="upload-wide" onClick={() => chooseUpload("knowledge")}>＋ رفع مستند {knowledgeView === "organization" ? "للشركة" : "شخصي"}</button>}
        {knowledgeView === "organization" && !canManageCompany && <p className="settings-note">يمكنك قراءة مصادر الشركة المسموح بها، لكن رفعها وإدارتها متاحان للمالك أو مسؤول المؤسسة فقط.</p>}
        <p className="settings-note">بعد اختيار الملف ستظهر نافذة لتحديد المجال والاستخدام قبل بدء الرفع.</p>
        <label>تصفية المصادر<select value={documentDomainFilter} onChange={(event) => setDocumentDomainFilter(event.target.value)}><option value="all">كل المجالات</option><option value="project">مشروع</option><option value="general">عام</option><option value="hr">موارد بشرية</option><option value="finance">مالية</option><option value="it">تقنية معلومات</option><option value="legal">قانوني</option><option value="operations">عمليات</option></select></label>
        <div className="document-list">
          {documents.filter((document) => document.owner_scope === knowledgeView && (documentDomainFilter === "all" || document.domain === documentDomainFilter)).length === 0 && <div className="document-empty">لا توجد ملفات في التصنيف المحدد.</div>}
          {documents.filter((document) => document.owner_scope === knowledgeView && (documentDomainFilter === "all" || document.domain === documentDomainFilter)).map((document) => (
            <div className="document" key={document.id}>
              <span className="file-icon">▤</span><div><strong>{document.name}</strong><small><i className={`status-dot ${document.status}`} /> {documentStatus(document)} · {document.domain} · {document.purpose} · {document.classification}</small>{document.owner_scope === "personal" && canManageCompany && <button className="revoke-source" onClick={() => void promoteDocument(document)}>نقل لمعرفة الشركة</button>}{(document.owner_scope === "personal" || canManageCompany) && <button className="revoke-source" onClick={() => void revokeDocument(document)}>إلغاء المصدر</button>}</div>
            </div>
          ))}
        </div>
        </div>
      </aside>

      <aside className={`knowledge-drawer ${integrationsOpen ? "drawer-open" : ""}`} aria-label={copy(locale, "تكاملات Jira وSlack", "Jira and Slack integrations")} aria-hidden={!integrationsOpen} inert={!integrationsOpen}>
        <div className="drawer-header"><div><small>SAAS CONNECTIONS</small><h2>Jira وSlack</h2></div><button onClick={() => setIntegrationsOpen(false)}>×</button></div>
        <p>{copy(locale, "كل اتصال معزول داخل المؤسسة، وبيانات التفويض مشفرة ولا تظهر مرة أخرى.", "Connections are tenant-isolated. Authorization data is encrypted and never shown again.")}</p>
        <IntegrationForm request={request} onCreated={refreshConnections} />
        <div className="document-list">
          {connections.length === 0 && <div className="document-empty">لا توجد اتصالات لهذه المؤسسة.</div>}
          {connections.map((connection) => (
            <IntegrationCard key={connection.id} connection={connection} request={request} refresh={refreshConnections} />
          ))}
        </div>
      </aside>

      {settingsOpen && <div className="settings-modal-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSettingsOpen(false); }}><section className="settings-modal company-settings-modal" role="dialog" aria-modal="true" aria-label={copy(locale, "إعدادات الشركة", "Company settings")} dir={locale === "ar" ? "rtl" : "ltr"}>
        <header><div><small>COMPANY CONTROL</small><h2>{copy(locale, "إعدادات الشركة", "Company settings")}</h2></div><button type="button" onClick={() => setSettingsOpen(false)} aria-label={copy(locale, "إغلاق", "Close")}>×</button></header>
        <div className="company-settings-content"><PlatformSettings request={request} profiles={aiProfiles} agents={agents} refresh={refreshSettings} sections={settingsSections} locale={locale} onNavigate={(code) => { setSettingsOpen(false); if (code === "integrations") setIntegrationsOpen(true); if (code === "knowledge") { setKnowledgeView("organization"); setKnowledgeOpen(true); } if (code === "jobs") setJobsOpen(true); }} counts={{ agents: agents.length, jobs: jobs.length, artifacts: artifacts.length }} /></div>
      </section></div>}

      <aside className={`knowledge-drawer jobs-drawer ${jobsOpen ? "drawer-open" : ""}`} aria-label={copy(locale, "المهام الخلفية", "Background jobs")} aria-hidden={!jobsOpen} inert={!jobsOpen}>
        <div className="drawer-header"><div><small>BACKGROUND OPERATIONS</small><h2>{copy(locale, "المهام الخلفية", "Background jobs")}</h2></div><button onClick={() => setJobsOpen(false)}>×</button></div>
        <p>{copy(locale, "تنفيذ طويل آمن مع تقدم قابل للاستئناف، إلغاء تعاوني، ومحاولات محدودة.", "Long-running work with resumable progress, cooperative cancellation, and bounded retries.")}</p>
        <button className="upload-wide" onClick={() => void refreshJobs()}>↻ {copy(locale, "تحديث الحالة", "Refresh status")}</button>
        <div className="job-list">
          {jobs.length === 0 && <div className="document-empty">لا توجد مهام خلفية بعد.</div>}
          {jobs.map((job) => <JobCard key={job.id} job={job} request={request} refresh={refreshJobs} />)}
        </div>
      </aside>

      <aside className={`knowledge-drawer artifacts-drawer ${artifactsOpen ? "drawer-open" : ""}`} aria-label={copy(locale, "المخرجات والإجراءات", "Outputs and actions")} aria-hidden={!artifactsOpen} inert={!artifactsOpen}>
        <div className="drawer-header"><div><small>GOVERNED OUTPUTS</small><h2>{copy(locale, "المخرجات والإجراءات", "Outputs and actions")}</h2></div><button onClick={() => setArtifactsOpen(false)}>×</button></div>
        <p>{copy(locale, "كل مخرج يبدأ كمسودة خاصة، ويحتاج مراجعة مستقلة قبل النشر أو التنفيذ.", "Every output starts as a private draft and requires independent review before publishing or execution.")}</p>
        <button className="upload-wide" onClick={() => void refreshArtifacts()}>↻ {copy(locale, "تحديث المخرجات", "Refresh outputs")}</button>
        <div className="artifact-list">
          {artifacts.length === 0 && <div className="document-empty">لا توجد مخرجات مرئية لك.</div>}
          {artifacts.map((artifact) => <ArtifactCard key={artifact.id} artifact={artifact} request={request} refresh={refreshArtifacts} />)}
        </div>
      </aside>
    </main>
  );
}

function ArtifactCard({ artifact, request, refresh }: {
  artifact: ArtifactItem;
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
  refresh: () => Promise<void>;
}) {
  const [status, setStatus] = useState("");
  const [destination, setDestination] = useState("");
  const [destinationType, setDestinationType] = useState<"email" | "channel" | "workspace" | "site" | "project" | "file">("email");
  const [action, setAction] = useState<"send" | "publish" | "activate" | "export" | "schedule">("send");
  const [executionProvider, setExecutionProvider] = useState<"dry_run" | "mcp">("dry_run");
  const [validatedAction, setValidatedAction] = useState<ArtifactAction | null>(null);
  const idempotencyKey = `ui-${artifact.id}-${action}-${destinationType}`;
  const submitReview = async () => {
    try {
      await request(`/api/v1/artifacts/${artifact.id}/review`, { method: "POST" });
      setStatus("تم إرسال المسودة للمراجعة المستقلة."); await refresh();
    } catch { setStatus("تعذر الإرسال؛ قد لا تكون المالك أو تغيرت الحالة."); }
  };
  const decide = async (decision: "approved" | "rejected") => {
    try {
      await request(`/api/v1/artifacts/${artifact.id}/review/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, comment: "Reviewed from governed artifacts UI" }) });
      setStatus(decision === "approved" ? "تم الاعتماد." : "تم الرفض وإعادته كمسودة."); await refresh();
    } catch { setStatus("تحتاج مسؤولًا مستقلًا؛ لا يمكن لصاحب المسودة اعتمادها."); }
  };
  const validateAction = async () => {
    try {
      const item = await request<ArtifactAction>(`/api/v1/artifacts/${artifact.id}/actions/validate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, destination_type: destinationType, destination, idempotency_key: idempotencyKey }) });
      setValidatedAction(item); setStatus("تم التحقق من الوجهة وحجز العملية بدون تنفيذ خارجي.");
    } catch { setStatus("فشل التحقق؛ يلزم مخرج معتمد ووجهة صحيحة وصلاحية مسؤول."); }
  };
  const executeAction = async () => {
    if (!validatedAction) return;
    try {
      const item = await request<ArtifactAction>(`/api/v1/artifacts/actions/${validatedAction.id}/execute`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ destination, idempotency_key: idempotencyKey, provider: executionProvider }) });
      setValidatedAction(item); setStatus(`${executionProvider === "mcp" ? "MCP" : "Dry-run"}: ${item.status} · محاولة ${item.attempt_count}/${item.max_attempts}${item.error_code ? ` · ${item.error_code}` : ""}`);
    } catch { setStatus("تعذر التنفيذ الآمن أو تغيرت الوجهة بعد التحقق."); }
  };
  const retryAction = async () => {
    if (!validatedAction) return;
    try {
      const item = await request<ArtifactAction>(`/api/v1/artifacts/actions/${validatedAction.id}/retry`, { method: "POST" });
      setValidatedAction(item); setStatus(`أُعيدت العملية إلى التحقق · محاولة ${item.attempt_count}/${item.max_attempts}. نفّذها مجددًا عند الجاهزية.`);
    } catch { setStatus("لا يمكن إعادة المحاولة؛ ربما استُنفد الحد أو لم تعد العملية في حالة فشل."); }
  };
  const compensateAction = async () => {
    if (!validatedAction) return;
    try {
      const item = await request<ArtifactAction>(`/api/v1/artifacts/actions/${validatedAction.id}/compensate`, { method: "POST" });
      setValidatedAction(item); setStatus(`حالة التعويض: ${item.status}.`);
    } catch { setStatus("تعذر التعويض. التنفيذ الحقيقي يحتاج عملية عكسية صريحة من المزود؛ Dry-run يدعم التعويض الآمن."); }
  };
  return <article className="artifact-card">
    <div><strong>{artifact.name}</strong><span className={`job-status ${artifact.status}`}>{artifact.status}</span></div>
    <small>{artifact.artifact_type} · {artifact.classification} · v{artifact.current_version}</small>
    <div className="artifact-actions">
      <a href={`${API_BASE_URL}/api/v1/artifacts/${artifact.id}/versions/${artifact.current_version}/download`}>تنزيل</a>
      {artifact.status === "draft" && <button onClick={() => void submitReview()}>إرسال للمراجعة</button>}
      {artifact.status === "in_review" && <><button onClick={() => void decide("approved")}>اعتماد</button><button className="danger" onClick={() => void decide("rejected")}>رفض</button></>}
    </div>
    {["approved", "published"].includes(artifact.status) && <div className="artifact-execution">
      <select value={action} onChange={(event) => { setAction(event.target.value as typeof action); setValidatedAction(null); }}><option value="send">إرسال</option><option value="publish">نشر</option><option value="activate">تفعيل</option><option value="export">تصدير</option><option value="schedule">جدولة</option></select>
      <select value={destinationType} onChange={(event) => { setDestinationType(event.target.value as typeof destinationType); setValidatedAction(null); }}><option value="email">Email</option><option value="channel">Channel</option><option value="workspace">Workspace</option><option value="site">Site</option><option value="project">Project</option><option value="file">File</option></select>
      <select value={executionProvider} onChange={(event) => { setExecutionProvider(event.target.value as typeof executionProvider); setValidatedAction(null); }}><option value="dry_run">اختبار آمن</option><option value="mcp">تنفيذ عبر MCP</option></select>
      <input value={destination} onChange={(event) => { setDestination(event.target.value); setValidatedAction(null); }} placeholder="الوجهة المعتمدة" dir="ltr" />
      <button onClick={() => void validateAction()} disabled={!destination}>تحقق وحجز</button>
      {validatedAction?.status === "validated" && <button onClick={() => void executeAction()}>{executionProvider === "mcp" ? "تنفيذ عبر MCP" : "تنفيذ Dry-run"}</button>}
      {validatedAction?.status === "failed" && validatedAction.attempt_count < validatedAction.max_attempts && <button onClick={() => void retryAction()}>إعادة محاولة صريحة</button>}
      {validatedAction?.status === "succeeded" && <button className="danger" onClick={() => void compensateAction()}>تعويض/تراجع</button>}
    </div>}
    {status && <em>{status}</em>}
  </article>;
}

function JobCard({ job, request, refresh }: {
  job: BackgroundJob;
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
  refresh: () => Promise<void>;
}) {
  const active = ["queued", "running", "retry_scheduled", "waiting_approval"].includes(job.status);
  const retryable = ["failed", "dead_letter"].includes(job.status);
  const percent = job.total_units ? Math.min(100, Math.round(job.completed_units * 100 / job.total_units)) : null;
  const act = async (action: "cancel" | "retry") => {
    await request(`/api/v1/jobs/${job.id}/${action}`, { method: "POST" });
    await refresh();
  };
  return <article className="job-card">
    <div className="job-heading"><strong>{jobKindLabel[job.kind] ?? job.kind}</strong><span className={`job-status ${job.status}`}>{jobStatusLabel[job.status] ?? job.status}</span></div>
    <small>{job.progress_stage} · أولوية {job.priority} · خطورة {job.risk}</small>
    <div className={`job-progress ${percent === null && active ? "indeterminate" : ""}`}><i style={{ width: `${percent ?? 0}%` }} /></div>
    <div className="job-meta"><span>{percent === null ? `تقدم غير محدد · ${job.completed_units} وحدة` : `${percent}%`}</span><time>{new Date(job.updated_at).toLocaleString("ar-EG")}</time></div>
    <div className="job-actions">
      {active && <button onClick={() => void act("cancel")}>إلغاء</button>}
      {retryable && <button className="retry" onClick={() => void act("retry")}>إعادة المحاولة</button>}
    </div>
  </article>;
}

const jobKindLabel: Record<string, string> = {
  document_ocr: "معالجة مستند", media: "معالجة وسائط", report_bi: "تقرير وتحليلات",
  integration_automation: "تكامل وأتمتة", risk_review: "مراجعة مخاطر",
};
const jobStatusLabel: Record<string, string> = {
  queued: "في الانتظار", running: "قيد التنفيذ", retry_scheduled: "إعادة مجدولة",
  waiting_approval: "ينتظر موافقة", completed: "مكتملة", failed: "فشلت",
  cancelled: "ملغاة", dead_letter: "تحتاج تدخل",
};

function PlatformSettings({ request, profiles, agents, refresh, sections, locale, onNavigate, counts }: {
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
  profiles: AIProfile[];
  agents: AgentCard[];
  refresh: () => Promise<void>;
  sections: SettingsSection[];
  locale: Locale;
  onNavigate: (code: string) => void;
  counts: { agents: number; jobs: number; artifacts: number };
}) {
  const [section, setSection] = useState<"overview" | "ai" | "artifacts" | "structure" | "people" | "agents">("overview");
  return <>
    <nav className="settings-tabs platform-settings-tabs" aria-label={copy(locale, "أقسام إعدادات الشركة", "Company settings sections")}>
      {sections.map((item) => <button key={item.code} type="button" aria-current={section === item.code ? "page" : undefined} className={section === item.code ? "active" : ""} onClick={() => item.code === "overview" || item.code === "ai" || item.code === "artifacts" || item.code === "structure" || item.code === "people" || item.code === "agents" ? setSection(item.code) : onNavigate(item.code)}>{copy(locale, item.label, ({ overview: "Overview", ai: "AI providers", artifacts: "Outputs", structure: "Organization", people: "People", agents: "Agents", integrations: "Integrations", knowledge: "Knowledge", jobs: "Jobs" } as Record<string, string>)[item.code] ?? item.label)}</button>)}
    </nav>
    {section === "overview" && sections.some((item) => item.code === "overview") && <div className="settings-overview"><h3>{copy(locale, "حالة إعدادات الشركة", "Company settings overview")}</h3><p>{copy(locale, `الوكلاء العاملون المتاحون: ${counts.agents} · المهام المرئية: ${counts.jobs} · المخرجات المرئية: ${counts.artifacts}`, `Available agents: ${counts.agents} · Visible jobs: ${counts.jobs} · Visible outputs: ${counts.artifacts}`)}</p><p>{copy(locale, "مزودات الذكاء المفعّلة:", "Enabled AI providers:")} {profiles.filter((item) => item.status === "enabled").map((item) => item.provider).join(" · ") || copy(locale, "لا يوجد", "None")}</p><p>{copy(locale, "هذه ملخصات مرئية لك فقط؛ صلاحية كل إجراء يعيد الخادم فحصها عند الاستخدام.", "These summaries are visible to you only; the server rechecks authorization for every action.")}</p></div>}
    {section === "ai" && sections.some((item) => item.code === "ai") && <AISettings request={request} profiles={profiles} agents={agents} refresh={refresh} />}
    {section === "artifacts" && sections.some((item) => item.code === "artifacts") && <ArtifactPolicySettings request={request} />}
    {section === "structure" && sections.some((item) => item.code === "structure") && <CompanyStructureSettings request={request} />}
    {section === "people" && sections.some((item) => item.code === "people") && <CompanyPeopleSettings request={request} />}
    {section === "agents" && sections.some((item) => item.code === "agents") && <CompanyAgentSettings request={request} agents={agents} />}
  </>;
}

function CompanyAgentSettings({ request, agents }: { request: <T>(path: string, init?: RequestInit) => Promise<T>; agents: AgentCard[] }) {
  const [assignments, setAssignments] = useState<AgentAssignment[]>([]);
  const [catalog, setCatalog] = useState<CompanyCatalogItem[]>([]);
  const [units, setUnits] = useState<CompanyUnit[]>([]);
  const [people, setPeople] = useState<CompanyPerson[]>([]);
  const [agentCode, setAgentCode] = useState("");
  const [targetType, setTargetType] = useState<"department" | "team" | "project" | "user">("department");
  const [targetId, setTargetId] = useState("");
  const [effect, setEffect] = useState<"allow" | "deny">("allow");
  const [status, setStatus] = useState("");
  const [catalogVersions, setCatalogVersions] = useState<Record<string, string>>({});
  const refresh = useCallback(async () => {
    const [assignmentRows, unitRows, personRows, catalogRows] = await Promise.all([
      request<AgentAssignment[]>("/api/v1/agent-catalog/assignments"),
      request<CompanyUnit[]>("/api/v1/company/units"),
      request<CompanyPerson[]>("/api/v1/company/people"),
      request<CompanyCatalogItem[]>("/api/v1/agent-catalog/catalog"),
    ]);
    setAssignments(assignmentRows); setUnits(unitRows); setPeople(personRows); setCatalog(catalogRows);
  }, [request]);
  useEffect(() => { void refresh().catch(() => setStatus("تعذر تحميل تعيينات الوكلاء.")); }, [refresh]);
  const targets = targetType === "user"
    ? people.filter((person) => person.status === "active").map((person) => ({ id: person.user_id, name: person.display_name }))
    : units.filter((unit) => unit.kind === targetType).map((unit) => ({ id: unit.id, name: unit.name }));
  const assign = async (event: FormEvent) => {
    event.preventDefault();
    if (!agentCode || !targetId || !window.confirm(`تأكيد ${effect === "allow" ? "منح" : "منع"} الوكيل ${agentCode} للجهة المختارة؟`)) return;
    try {
      await request("/api/v1/agent-catalog/assignments", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_code: agentCode, target_type: targetType, target_id: targetId,
          actions: ["visible", "use", "read", "draft"], effect, classification_ceiling: "internal" }),
      });
      setStatus("تم حفظ التعيين؛ يراجع الخادم الصلاحية مجددًا عند الاستخدام.");
      await refresh();
    } catch { setStatus("تعذر تعيين الوكيل. تحقق من حالته وصلاحياتك والجهة المستهدفة."); }
  };
  const revoke = async (row: AgentAssignment) => {
    if (!window.confirm(`هل تريد سحب تعيين ${row.agent_code} من ${row.target_type}؟`)) return;
    try {
      await request(`/api/v1/agent-catalog/assignments/${row.id}`, { method: "DELETE" });
      setStatus("تم سحب التعيين."); await refresh();
    } catch { setStatus("تعذر سحب التعيين."); }
  };
  const installAgent = async (item: CompanyCatalogItem) => {
    const version = catalogVersions[item.code] ?? item.selected_version;
    if (!window.confirm(`تثبيت ${item.name} بإصدار ${version}؟ سيبدأ معطلاً حتى تفعيله صراحةً.`)) return;
    try { await request("/api/v1/agent-catalog/install", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ agent_code: item.code, version }) }); setStatus("تم التثبيت مع إبقاء الوكيل معطلاً افتراضيًا."); await refresh(); }
    catch { setStatus("تعذر التثبيت. تحقق من الإصدار وصلاحية مسؤول المؤسسة."); }
  };
  const toggleAgent = async (item: CompanyCatalogItem) => {
    const enabled = !item.enabled;
    if (!window.confirm(`${enabled ? "تفعيل" : "تعطيل"} ${item.name}؟ سيعاد فحص السياسة عند الاستخدام.`)) return;
    try { await request(`/api/v1/agent-catalog/${item.code}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled }) }); setStatus(enabled ? "تم تفعيل الوكيل." : "تم تعطيل الوكيل؛ التعيينات محفوظة حتى إعادة التفعيل أو سحبها."); await refresh(); }
    catch { setStatus("تعذر تغيير حالة الوكيل."); }
  };
  return <div className="company-structure">
    <h3>كتالوج الوكلاء وإدارتهم</h3><p className="settings-note">التثبيت لا يفعّل الوكيل تلقائيًا. بعد التثبيت راجع الإصدار ثم فعّله؛ إيقافه لا يحذف تعييناته.</p>
    <div className="structure-list agent-catalog-list">{catalog.map((item) => <article key={item.code}><strong>{item.name} · {item.category}</strong><small>{item.description}</small><small>{item.installed ? `مثبت · إصدار ${item.selected_version} · ${item.enabled ? "مفعّل" : "متوقف"}` : "غير مثبت"}</small><div className="settings-row">{!item.installed && <><select aria-label={`إصدار ${item.name}`} value={catalogVersions[item.code] ?? item.selected_version} onChange={(event) => setCatalogVersions((value) => ({ ...value, [item.code]: event.target.value }))}>{item.versions.map((version) => <option key={version} value={version}>{version}</option>)}</select><button type="button" onClick={() => void installAgent(item)}>تثبيت</button></>}{item.installed && <button type="button" className={item.enabled ? "danger" : "settings-action"} onClick={() => void toggleAgent(item)}>{item.enabled ? "تعطيل" : "تفعيل"}</button>}</div></article>)}</div>
    <h3>تعيين صلاحيات الوكلاء</h3><p className="settings-note">التعيين يحدد الرؤية والاستخدام والقراءة والمسودة؛ التنفيذ والنشر يتطلبان سياسة وموافقة منفصلتين.</p>
    <form className="structure-form" onSubmit={(event) => void assign(event)}>
      <label>الوكيل<select value={agentCode} onChange={(event) => setAgentCode(event.target.value)} required><option value="">اختر وكيلاً</option>{agents.map((agent) => <option key={agent.code} value={agent.code}>{agent.name} · {agent.category}</option>)}</select></label>
      <label>نوع الجهة<select value={targetType} onChange={(event) => { setTargetType(event.target.value as typeof targetType); setTargetId(""); }}><option value="department">قسم</option><option value="team">فريق</option><option value="project">مشروع</option><option value="user">موظف</option></select></label>
      <label>الجهة<select value={targetId} onChange={(event) => setTargetId(event.target.value)} required><option value="">اختر الجهة</option>{targets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>القرار<select value={effect} onChange={(event) => setEffect(event.target.value as typeof effect)}><option value="allow">سماح</option><option value="deny">منع</option></select></label>
      <button className="settings-action" type="submit">حفظ التعيين</button>
    </form>
    {status && <p role="status" className="settings-note">{status}</p>}
    <div className="structure-list agent-assignment-list">{assignments.map((row) => <article key={row.id}><strong>{row.agent_code} · {row.effect === "allow" ? "سماح" : "منع"}</strong><small>{row.target_type} · {row.target_id} · {row.actions.join("، ")} · {row.active ? "فعال" : "مسحوب"}</small>{row.active && <button type="button" className="danger" onClick={() => void revoke(row)}>سحب التعيين</button>}</article>)}</div>
  </div>;
}

function CompanyPeopleSettings({ request }: { request: <T>(path: string, init?: RequestInit) => Promise<T> }) {
  const [people, setPeople] = useState<CompanyPerson[]>([]);
  const [departments, setDepartments] = useState<CompanyUnit[]>([]);
  const [units, setUnits] = useState<CompanyUnit[]>([]);
  const [invitations, setInvitations] = useState<CompanyInvitation[]>([]);
  const [departmentId, setDepartmentId] = useState("");
  const [createdLink, setCreatedLink] = useState("");
  const [status, setStatus] = useState("");
  const [roleToGrant, setRoleToGrant] = useState<Record<string, "organization_admin" | "integration_manager">>({});
  const [roleHistory, setRoleHistory] = useState<{ userId: string; name: string; rows: CompanyRoleHistory[] } | null>(null);
  const [accessPreview, setAccessPreview] = useState<{ name: string; result: CompanyAccessPreview } | null>(null);
  const [previewRole, setPreviewRole] = useState("organization_admin");
  const [previewOperation, setPreviewOperation] = useState<"add" | "remove">("add");
  const [previewScopeKind, setPreviewScopeKind] = useState<"department" | "team" | "project">("department");
  const [previewScopeId, setPreviewScopeId] = useState("");
  const [previewScopeOperation, setPreviewScopeOperation] = useState<"add" | "remove">("add");
  const refresh = useCallback(async () => {
    const [peopleRows, unitRows, invitationRows] = await Promise.all([
      request<CompanyPerson[]>("/api/v1/company/people"),
      request<CompanyUnit[]>("/api/v1/company/units"),
      request<CompanyInvitation[]>("/api/v1/company/invitations"),
    ]);
    setPeople(peopleRows); setUnits(unitRows); setDepartments(unitRows.filter((item) => item.kind === "department"));
    setInvitations(invitationRows);
  }, [request]);
  useEffect(() => {
    void refresh().catch(() => setStatus("تعذر تحميل إدارة الموظفين."));
  }, [refresh]);
  const createInvitation = async (event: FormEvent) => {
    event.preventDefault(); setCreatedLink("");
    try {
      const invite = await request<{ id: string; link: string; expires_at: string }>("/api/v1/company/invitations", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ department_id: departmentId }),
      });
      setCreatedLink(invite.link); setStatus("تم إنشاء رابط لمرة واحدة وصالح 72 ساعة. انسخه الآن؛ لن يظهر ثانية.");
      await refresh();
    } catch { setStatus("تعذر إنشاء الرابط. تحقق من صلاحيتك والقسم المحدد."); }
  };
  const copyInvitation = async () => {
    try { await navigator.clipboard.writeText(createdLink); setStatus("تم نسخ رابط الدعوة."); }
    catch { setStatus("تعذر النسخ تلقائيًا؛ انسخ الرابط من الحقل يدويًا."); }
  };
  const revokeInvitation = async (invite: CompanyInvitation) => {
    if (!window.confirm(`إلغاء رابط الانضمام لقسم ${invite.department_name}؟`)) return;
    try { await request(`/api/v1/company/invitations/${invite.id}`, { method: "DELETE" }); setStatus("تم إلغاء الرابط."); await refresh(); }
    catch { setStatus("تعذر إلغاء الرابط."); }
  };
  const setMemberStatus = async (person: CompanyPerson) => {
    const next = person.status === "active" ? "suspended" : "active";
    const verb = next === "suspended" ? "تعليق" : "إعادة تفعيل";
    if (!window.confirm(`${verb} ${person.display_name}؟ ${next === "suspended" ? "سيتم إنهاء جلساته الحالية فورًا." : "سيستطيع تسجيل الدخول مجددًا."}`)) return;
    try {
      await request(`/api/v1/company/people/${person.user_id}/status`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: next }) });
      setStatus(next === "suspended" ? "تم تعليق العضوية وإبطال جلساتها." : "تمت إعادة تفعيل العضوية."); await refresh();
    } catch { setStatus("تعذر تغيير الحالة. يلزم Owner مع تحقق إضافي؛ ولا يمكن تعليق آخر Owner."); }
  };
  const showRoleHistory = async (person: CompanyPerson) => {
    try { const rows = await request<CompanyRoleHistory[]>(`/api/v1/company/people/${person.user_id}/roles`); setRoleHistory({ userId: person.user_id, name: person.display_name, rows }); }
    catch { setStatus("تعذر تحميل سجل الأدوار."); }
  };
  const previewAccess = async (person: CompanyPerson, roleCode?: string, operation?: "add" | "remove", scopeKind?: "department" | "team" | "project", scopeId?: string, scopeOperation?: "add" | "remove") => {
    const scenario = roleCode && operation ? { role_code: roleCode, operation } : scopeKind && scopeId && scopeOperation ? { scope_kind: scopeKind, scope_id: scopeId, scope_operation: scopeOperation } : {};
    try { const result = await request<CompanyAccessPreview>(`/api/v1/company/people/${person.user_id}/access-preview`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(scenario) }); setAccessPreview({ name: person.display_name, result }); }
    catch { setStatus("تعذر معاينة الصلاحيات الحالية لهذا الموظف."); }
  };
  const grantRole = async (person: CompanyPerson) => {
    const role = roleToGrant[person.user_id] ?? "organization_admin";
    if (!window.confirm(`منح دور ${role} إلى ${person.display_name}؟ سيمنح هذا صلاحيات إدارية للمؤسسة.`)) return;
    try {
      await request("/api/v1/company/roles", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: person.user_id, role }) });
      setStatus("تم منح الدور. يلزم Owner مع تحقق إضافي."); await refresh();
    } catch { setStatus("تعذر منح الدور. يلزم Owner بتحقق إضافي، ولا يمكن منح دورك لنفسك."); }
  };
  const revokeRole = async (id: string) => {
    if (!window.confirm("سحب هذا الدور؟ يتطلب Owner وتحققًا إضافيًا.")) return;
    try { await request(`/api/v1/company/roles/${id}`, { method: "DELETE" }); setStatus("تم سحب الدور."); if (roleHistory) { const person = people.find((item) => item.user_id === roleHistory.userId); if (person) await showRoleHistory(person); } await refresh(); }
    catch { setStatus("تعذر سحب الدور. لا يمكن سحب آخر دور Owner."); }
  };
  const selectedPreviewPerson = people.find((person) => person.user_id === accessPreview?.result.user_id);
  const scopeUnits = units.filter((unit) => unit.kind === previewScopeKind);
  return <div className="company-structure">
    <h3>موظفو المؤسسة</h3>
    <p className="settings-note">الدعوات تنضم إلى هذه المؤسسة والقسم المحدد. لا يُرسل بريد؛ شارك الرابط يدويًا. الرابط يستخدم مرة واحدة وينتهي خلال 72 ساعة، ويلزم تسجيل الدخول عبر مزود الهوية للشركة.</p>
    <form className="structure-form" onSubmit={(event) => void createInvitation(event)}>
      <label>القسم الذي سينضم إليه الموظف<select value={departmentId} onChange={(event) => setDepartmentId(event.target.value)} required><option value="">اختر القسم</option>{departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <button className="settings-action" type="submit">إنشاء رابط انضمام</button>
    </form>
    {createdLink && <div className="invitation-link"><label>رابط الدعوة (يظهر مرة واحدة)<input value={createdLink} readOnly dir="ltr" onFocus={(event) => event.currentTarget.select()} /></label><button type="button" onClick={() => void copyInvitation()}>نسخ الرابط</button></div>}
    {status && <p role="status">{status}</p>}
    <h4>الروابط الصادرة</h4>
    <div className="structure-list">{invitations.map((invite) => <article key={invite.id}><strong>{invite.department_name} · {invite.status}</strong><small>ينتهي {new Date(invite.expires_at).toLocaleString("ar-EG")}</small>{invite.status === "pending" && <button type="button" className="danger" onClick={() => void revokeInvitation(invite)}>إلغاء الرابط</button>}</article>)}</div>
    <h4>الموظفون الحاليون</h4>
    <div className="structure-list">{people.map((person) => <article key={person.user_id}>
      <strong>{person.display_name}</strong><small>{person.email || "بلا بريد"} · {person.status} · {person.classification_clearance}</small>
      <small>الأدوار: {person.role_codes.join("، ") || "موظف"}</small>
      <div className="settings-row"><button type="button" onClick={() => void previewAccess(person)}>معاينة وصوله</button><button type="button" onClick={() => void showRoleHistory(person)}>سجل الأدوار</button><button type="button" className={person.status === "active" ? "danger" : "settings-action"} onClick={() => void setMemberStatus(person)}>{person.status === "active" ? "تعليق" : "إعادة تفعيل"}</button>
        <select aria-label={`الدور الجديد لـ ${person.display_name}`} value={roleToGrant[person.user_id] ?? "organization_admin"} onChange={(event) => setRoleToGrant((value) => ({ ...value, [person.user_id]: event.target.value as "organization_admin" | "integration_manager" }))}><option value="organization_admin">مدير المؤسسة</option><option value="integration_manager">مدير التكاملات</option></select><button type="button" onClick={() => void grantRole(person)}>منح الدور</button>
      </div>
    </article>)}</div>
    {accessPreview && <div className="invitation-overlay" role="dialog" aria-modal="true" aria-labelledby="access-preview-title"><section>
      <h3 id="access-preview-title">معاينة وصول {accessPreview.name}</h3>
      <p className="settings-note">المعاينة للقراءة فقط ولا تغيّر أي صلاحية. تقارن الوكلاء والأفعال بحسب الدور أو عضوية تنظيمية واحدة. منح الأدوات المعروضة هي الحالية فقط، ولا تحاكي هذه الشاشة صلاحية المستندات ومصادر المعرفة. إصدار السياسة {accessPreview.result.policy_version}.</p>
      <div className="settings-row"><label>محاكاة دور<select value={previewRole} onChange={(event) => setPreviewRole(event.target.value)}><option value="organization_admin">مدير المؤسسة</option><option value="integration_manager">مدير التكاملات</option><option value="department_manager">مدير قسم</option><option value="team_manager">مدير فريق</option><option value="project_manager">مدير مشروع</option><option value="employee">موظف</option><option value="auditor_risk_reviewer">مراجع مخاطر</option></select></label>
        <select aria-label="نوع تغيير الدور" value={previewOperation} onChange={(event) => setPreviewOperation(event.target.value as "add" | "remove")}><option value="add">إضافة مؤقتة للمقارنة</option><option value="remove">إزالة مؤقتة للمقارنة</option></select>
        <button type="button" onClick={() => { if (selectedPreviewPerson) void previewAccess(selectedPreviewPerson, previewRole, previewOperation); }}>مقارنة أثر الدور</button>
      </div>
      <div className="settings-row"><label>نوع العضوية<select value={previewScopeKind} onChange={(event) => { const kind = event.target.value as "department" | "team" | "project"; setPreviewScopeKind(kind); setPreviewScopeId(""); }}><option value="department">قسم</option><option value="team">فريق</option><option value="project">مشروع</option></select></label>
        <label>الوحدة التنظيمية<select value={previewScopeId} onChange={(event) => setPreviewScopeId(event.target.value)}><option value="">اختر وحدة</option>{scopeUnits.map((unit) => <option key={unit.id} value={unit.id}>{unit.name}{unit.department_id ? ` · ${departments.find((department) => department.id === unit.department_id)?.name ?? "قسم"}` : ""}</option>)}</select></label>
        <select aria-label="نوع تغيير العضوية" value={previewScopeOperation} onChange={(event) => setPreviewScopeOperation(event.target.value as "add" | "remove")}><option value="add">إضافة افتراضية</option><option value="remove">إزالة افتراضية</option></select>
        <button type="button" disabled={!previewScopeId} onClick={() => { if (selectedPreviewPerson) void previewAccess(selectedPreviewPerson, undefined, undefined, previewScopeKind, previewScopeId, previewScopeOperation); }}>محاكاة أثر العضوية</button>
      </div>
      <p className="settings-note">إضافة فريق أو مشروع تتطلب عضوية الموظف في قسمه. إزالة القسم تستبعد كذلك فرق ومشاريع ذلك القسم في المحاكاة. لن تُحفظ تغييرات. يجب اختيار السيناريو المناسب لحالة العضوية الفعلية.</p>
      <h4>الوصول الحالي</h4>{accessPreview.result.agents.map((agent) => <article key={agent.code}><strong>{agent.name}</strong><small>{agent.category} · {agent.allowed_actions.join("، ") || "لا توجد أفعال"}</small></article>)}
      <h4>صلاحيات أدوات التكامل الفعالة حاليًا</h4>{accessPreview.result.tool_grants.map((grant, index) => <article key={`${grant.provider}-${grant.connection_name}-${grant.tool_name}-${index}`}><strong>{grant.provider} · {grant.connection_name} · {grant.tool_name}</strong><small>الصلاحية: {grant.permission}</small></article>)}
      {accessPreview.result.tools_truncated && <p role="status">تم اختصار قائمة منح الأدوات للحد من حجم المعاينة.</p>}
      {(accessPreview.result.role_operation || accessPreview.result.scope_operation) && <><h4>الوصول بعد المحاكاة</h4>
        {accessPreview.result.proposed_scope_kind && <p>السيناريو: {accessPreview.result.scope_operation === "add" ? "إضافة" : "إزالة"} عضوية {accessPreview.result.proposed_scope_kind} «{units.find((unit) => unit.id === accessPreview.result.proposed_scope_id)?.name ?? "وحدة تنظيمية"}» — معاينة فقط.</p>}
        {accessPreview.result.proposed_agents.map((agent) => <article key={agent.code}><strong>{agent.name}</strong><small>{agent.category} · {agent.allowed_actions.join("، ") || "لا توجد أفعال"}</small></article>)}
        <p>وكلاء يضاف الوصول إليها: {accessPreview.result.gained_agents.join("، ") || "لا يوجد"}</p><p>وكلاء يفقد الوصول إليها: {accessPreview.result.lost_agents.join("، ") || "لا يوجد"}</p>
        {accessPreview.result.action_changes.map((change) => <article key={change.code}><strong>{change.name}</strong><small>أفعال مضافة: {change.gained_actions.join("، ") || "لا يوجد"} · أفعال مسحوبة: {change.lost_actions.join("، ") || "لا يوجد"}</small></article>)}
      </>}
      <button type="button" onClick={() => setAccessPreview(null)}>إغلاق</button>
    </section></div>}
    {roleHistory && <div className="invitation-overlay" role="dialog" aria-modal="true" aria-labelledby="role-history-title"><section><h3 id="role-history-title">سجل أدوار {roleHistory.name}</h3>{roleHistory.rows.map((row) => <article key={row.id}><strong>{row.role_code}</strong><small>{new Date(row.valid_from).toLocaleString("ar-EG")} · {row.revoked_at ? `مسحوب ${new Date(row.revoked_at).toLocaleString("ar-EG")}` : "فعال"}</small>{!row.revoked_at && row.role_code !== "owner" && <button type="button" className="danger" onClick={() => void revokeRole(row.id)}>سحب الدور</button>}</article>)}<button type="button" onClick={() => setRoleHistory(null)}>إغلاق</button></section></div>}
  </div>;
}

function CompanyStructureSettings({ request }: { request: <T>(path: string, init?: RequestInit) => Promise<T> }) {
  const [units, setUnits] = useState<CompanyUnit[]>([]);
  const [people, setPeople] = useState<CompanyPerson[]>([]);
  const [kind, setKind] = useState<CompanyUnit["kind"]>("department");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [managerId, setManagerId] = useState("");
  const [ceiling, setCeiling] = useState("internal");
  const [status, setStatus] = useState("");
  const [memberUnitId, setMemberUnitId] = useState("");
  const [memberUserId, setMemberUserId] = useState("");
  const refresh = useCallback(async () => {
    const [unitItems, peopleItems] = await Promise.all([
      request<CompanyUnit[]>("/api/v1/company/units"),
      request<CompanyPerson[]>("/api/v1/company/people"),
    ]);
    setUnits(unitItems); setPeople(peopleItems);
  }, [request]);
  useEffect(() => { void refresh().catch(() => setStatus("تعذر تحميل هيكل الشركة.")); }, [refresh]);
  const create = async (event: FormEvent) => {
    event.preventDefault();
    const body = kind === "department"
      ? { code: code.trim().toUpperCase(), name: name.trim(), classification_ceiling: ceiling, manager_user_id: managerId || null }
      : kind === "project"
        ? { department_id: departmentId, code: code.trim().toUpperCase(), name: name.trim(), manager_user_id: managerId || null }
        : { department_id: departmentId, name: name.trim(), manager_user_id: managerId || null };
    try {
      await request(`/api/v1/company/${kind === "department" ? "departments" : kind === "team" ? "teams" : "projects"}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      setName(""); setCode(""); setManagerId(""); setStatus("تم إنشاء الوحدة داخل المؤسسة.");
      await refresh();
    } catch { setStatus("تعذر الإنشاء. راجع الرمز، القسم الأب ومعرّف المدير وصلاحياته."); }
  };
  const departments = units.filter((item) => item.kind === "department");
  const assignMember = async (event: FormEvent) => {
    event.preventDefault();
    const unit = units.find((item) => item.id === memberUnitId);
    if (!unit) return;
    try {
      await request(`/api/v1/company/${unit.kind}/${unit.id}/members`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: memberUserId }),
      });
      setStatus("تم تعيين العضوية بعد التحقق من حدود المؤسسة والقسم.");
    } catch { setStatus("تعذر تعيين العضوية؛ الفريق يتطلب عضوية القسم الأب أولًا."); }
  };
  return <div className="company-structure">
    <h3>الأقسام والفرق والمشاريع</h3><p className="settings-note">كل فريق أو مشروع يتبع قسمًا واحدًا. تعيين المدير اختياري ويتحقق منه الخادم قبل الحفظ.</p>
    <form className="structure-form" onSubmit={(event) => void create(event)}>
      <label>نوع الوحدة<select value={kind} onChange={(event) => setKind(event.target.value as CompanyUnit["kind"])}><option value="department">قسم</option><option value="team">فريق</option><option value="project">مشروع</option></select></label>
      <label>الاسم<input value={name} onChange={(event) => setName(event.target.value)} minLength={2} required /></label>
      {kind !== "team" && <label>الرمز<input value={code} onChange={(event) => setCode(event.target.value)} pattern="[A-Za-z0-9-]{2,32}" required dir="ltr" /></label>}
      {kind !== "department" && <label>القسم الأب<select value={departmentId} onChange={(event) => setDepartmentId(event.target.value)} required><option value="">اختر القسم</option>{departments.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.code})</option>)}</select></label>}
      {kind === "department" && <label>حد السرية<select value={ceiling} onChange={(event) => setCeiling(event.target.value)}><option value="public">عام</option><option value="internal">داخلي</option><option value="confidential">سري</option><option value="restricted">مقيد</option></select></label>}
      <label>المدير (اختياري)<select value={managerId} onChange={(event) => setManagerId(event.target.value)}><option value="">غير معين</option>{people.filter((person) => person.status === "active").map((person) => <option key={person.user_id} value={person.user_id}>{person.display_name}</option>)}</select></label>
      <button className="settings-action" type="submit">إنشاء {kind === "department" ? "قسم" : kind === "team" ? "فريق" : "مشروع"}</button>
    </form>
    <form className="structure-form" onSubmit={(event) => void assignMember(event)}><h3>تعيين عضو</h3><label>الوحدة<select value={memberUnitId} onChange={(event) => setMemberUnitId(event.target.value)} required><option value="">اختر القسم أو الفريق أو المشروع</option>{units.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.kind}</option>)}</select></label><label>الموظف<select value={memberUserId} onChange={(event) => setMemberUserId(event.target.value)} required><option value="">اختر موظفًا</option>{people.filter((person) => person.status === "active").map((person) => <option key={person.user_id} value={person.user_id}>{person.display_name}</option>)}</select></label><button className="settings-action" type="submit">تعيين العضوية</button></form>
    {status && <p role="status" className="settings-note">{status}</p>}
    <div className="structure-list">{units.map((item) => <article key={item.id}><strong>{item.name}</strong><small>{item.kind} · {item.code} · المدير: {item.manager_user_id || "غير معين"}</small></article>)}</div>
  </div>;
}

function ArtifactPolicySettings({ request }: {
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
}) {
  const [policy, setPolicy] = useState<ArtifactPolicy | null>(null);
  const [templates, setTemplates] = useState<ArtifactTemplate[]>([]);
  const [usage, setUsage] = useState<ArtifactUsage | null>(null);
  const [templateName, setTemplateName] = useState("");
  const [templateBody, setTemplateBody] = useState("## ملخص تنفيذي\n\n{{content}}\n\n## القرارات");
  const [mappingTool, setMappingTool] = useState("");
  const [mappingAction, setMappingAction] = useState<"send" | "publish" | "activate" | "export" | "schedule">("send");
  const [mappingDestination, setMappingDestination] = useState<"email" | "channel" | "workspace" | "site" | "project" | "file">("channel");
  const [status, setStatus] = useState("جاري تحميل سياسة الشركة…");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    void Promise.all([
      request<ArtifactPolicy>("/api/v1/artifacts/policy/current"),
      request<ArtifactTemplate[]>("/api/v1/artifacts/templates"),
      request<ArtifactUsage>("/api/v1/artifacts/usage/current-month"),
    ])
      .then(([value, templateItems, totals]) => { if (active) { setPolicy(value); setTemplates(templateItems); setUsage(totals); setStatus("السياسة الفعالة على مستوى الشركة"); } })
      .catch(() => { if (active) setStatus("تعذر تحميل السياسة أو ليست لديك صلاحية عرضها."); });
    return () => { active = false; };
  }, [request]);

  const update = <K extends keyof ArtifactPolicy>(key: K, value: ArtifactPolicy[K]) => {
    setPolicy((current) => current ? { ...current, [key]: value } : current);
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!policy || saving) return;
    setSaving(true);
    setStatus("جاري التحقق وحفظ السياسة…");
    try {
      const saved = await request<ArtifactPolicy>("/api/v1/artifacts/policy/current", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          brand_name: policy.brand_name,
          footer_text: policy.footer_text,
          require_classification_mark: policy.require_classification_mark,
          retention_days: policy.retention_days,
          monthly_artifact_limit: policy.monthly_artifact_limit,
        }),
      });
      setPolicy(saved);
      setStatus("تم حفظ السياسة. ستُطبق على المخرجات الجديدة تلقائيًا.");
    } catch {
      setStatus("لم يتم الحفظ. يلزم دور Owner أو Organization Admin وقيم ضمن الحدود.");
    } finally {
      setSaving(false);
    }
  };
  const createTemplate = async () => {
    if (!templateName.trim() || !templateBody.includes("{{content}}")) {
      setStatus("القالب يحتاج اسمًا وموضع {{content}} واحدًا.");
      return;
    }
    try {
      const created = await request<ArtifactTemplate>("/api/v1/artifacts/templates", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: templateName, artifact_type: "report", output_format: "markdown", body: templateBody }),
      });
      setTemplates((items) => [...items, created]); setTemplateName(""); setStatus("تم إنشاء القالب المؤسسي.");
    } catch { setStatus("تعذر إنشاء القالب. تحقق من الصلاحية والاسم وموضع المحتوى."); }
  };
  const saveMapping = async (active: boolean) => {
    if (!mappingTool.trim()) { setStatus("أدخل الاسم المؤهل للأداة كما يظهر في صفحة التكاملات."); return; }
    try {
      const saved = await request<ActionMapping>("/api/v1/artifacts/action-provider-mappings/current", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: mappingAction, destination_type: mappingDestination, tool_name: mappingTool.trim(), destination_field: mappingDestination === "email" ? "email" : `${mappingDestination}_id`, content_field: "text", active }),
      });
      setStatus(`تم ${saved.active ? "تفعيل" : "تعطيل"} ربط ${saved.action}/${saved.destination_type}.`);
    } catch { setStatus("تعذر حفظ الربط. يلزم دور مسؤول واسم أداة MCP ممنوح للمؤسسة."); }
  };

  if (!policy) return <div className="ai-settings"><p className="settings-note">{status}</p></div>;
  return <form className="ai-settings" onSubmit={save}>
    <div className="provider-status"><i /><strong>سياسة المؤسسة</strong><span>{status}</span></div>
    <p className="settings-note">هذه القواعد تُطبق في الخادم خارج محتوى الموديل. تعديلها متاح فقط لمسؤول الشركة.</p>
    <label>اسم العلامة التجارية<input value={policy.brand_name} maxLength={120} onChange={(event) => update("brand_name", event.target.value)} required /></label>
    <label>تذييل المخرجات<textarea value={policy.footer_text} maxLength={500} rows={3} onChange={(event) => update("footer_text", event.target.value)} /></label>
    <label className="settings-check"><input type="checkbox" checked={policy.require_classification_mark} onChange={(event) => update("require_classification_mark", event.target.checked)} /><span>إظهار درجة تصنيف البيانات على كل مخرج</span></label>
    <label>مدة الاحتفاظ بالأيام<input type="number" min={1} max={3650} value={policy.retention_days} onChange={(event) => update("retention_days", Number(event.target.value))} required /></label>
    <label>الحد الشهري للمخرجات<input type="number" min={1} max={100000} value={policy.monthly_artifact_limit} onChange={(event) => update("monthly_artifact_limit", Number(event.target.value))} required /></label>
    <button className="settings-action" type="submit" disabled={saving}>{saving ? "جاري الحفظ…" : "حفظ سياسة المخرجات"}</button>
    {usage && <div className="agents-summary"><div><strong>استخدام الشهر الحالي</strong><span>{usage.artifact_count} مخرج · {usage.stored_bytes.toLocaleString("ar-EG")} بايت · تكلفة مقدرة {(usage.estimated_cost_micros / 1_000_000).toFixed(2)}</span></div></div>}
    <hr className="settings-divider" />
    <strong>قوالب التقارير</strong>
    <div className="active-profiles">{templates.map((item) => <div key={item.id}><strong>{item.name}</strong><span>{item.output_format} · {item.active ? "فعال" : "متوقف"}</span></div>)}</div>
    <label>اسم القالب<input value={templateName} maxLength={120} onChange={(event) => setTemplateName(event.target.value)} /></label>
    <label>بنية القالب<textarea value={templateBody} maxLength={100000} rows={6} dir="auto" onChange={(event) => setTemplateBody(event.target.value)} /></label>
    <p className="settings-note">يجب وجود <code>{"{{content}}"}</code> مرة واحدة؛ يستبدله الخادم بالمحتوى ثم يطبق الهوية والتصنيف.</p>
    <button className="settings-action secondary" type="button" onClick={() => void createTemplate()}>إضافة قالب تقرير</button>
    <hr className="settings-divider" />
    <strong>ربط التنفيذ الخارجي عبر MCP</strong>
    <p className="settings-note">اربط كل إجراء ووجهة باسم أداة مؤهل ظاهر في التكاملات. يعيد الخادم فحص الاتصال والمنح قبل كل تنفيذ ويفشل مغلقًا عند سحب الصلاحية.</p>
    <select value={mappingAction} onChange={(event) => setMappingAction(event.target.value as typeof mappingAction)}><option value="send">إرسال</option><option value="publish">نشر</option><option value="activate">تفعيل</option><option value="export">تصدير</option><option value="schedule">جدولة</option></select>
    <select value={mappingDestination} onChange={(event) => setMappingDestination(event.target.value as typeof mappingDestination)}><option value="email">Email</option><option value="channel">Channel</option><option value="workspace">Workspace</option><option value="site">Site</option><option value="project">Project</option><option value="file">File</option></select>
    <label>اسم أداة MCP المؤهل<input value={mappingTool} maxLength={255} dir="ltr" placeholder="slack_xxxxxxxx__send_message" onChange={(event) => setMappingTool(event.target.value)} /></label>
    <div className="artifact-actions"><button type="button" onClick={() => void saveMapping(true)}>حفظ وتفعيل</button><button className="danger" type="button" onClick={() => void saveMapping(false)}>تعطيل الربط</button></div>
    <p className="settings-note">الحذف المجدول وLegal Hold فعالان في الخادم، وتظل بيانات النسب والمراجعة محفوظة بعد إزالة الملف.</p>
  </form>;
}

function AISettings({ request, profiles, agents, refresh }: {
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
  profiles: AIProfile[];
  agents: AgentCard[];
  refresh: () => Promise<void>;
}) {
  const [kind, setKind] = useState<"llm" | "embedding">("llm");
  const [provider, setProvider] = useState<"lm_studio" | "openai" | "claude">("lm_studio");
  const [model, setModel] = useState("tactiqo-chat");
  const [endpoint, setEndpoint] = useState("http://host.docker.internal:1234/v1");
  const [apiKey, setApiKey] = useState("");
  const [secretReference, setSecretReference] = useState<string | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [status, setStatus] = useState("جاهز للاختبار");
  const [testText, setTestText] = useState("اكتب ردًا عربيًا قصيرًا يؤكد أن Tactiqo يعمل محليًا.");
  const [result, setResult] = useState("");
  const profileName = kind === "embedding"
    ? "multilingual_embedding_model"
    : provider === "openai"
      ? "openai_visual_llm"
      : provider === "claude"
        ? "claude_analysis_llm"
        : "default_reasoning_llm";
  const capabilities = kind === "embedding"
    ? ["general"]
    : provider === "openai"
      ? ["general", "reasoning", "presentation_composition"]
      : provider === "claude"
        ? ["general", "reasoning", "document_analysis", "structured_extraction"]
        : ["general", "fast_chat", "reasoning", "document_analysis", "presentation_composition"];

  useEffect(() => {
    const active = profiles.find((item) => item.name === profileName);
    if (active) {
      setModel(active.model);
      setEndpoint(active.endpoint);
      setProvider(active.provider === "openai" || active.provider === "claude" ? active.provider : "lm_studio");
      setSecretReference(active.has_secret_reference ? "configured" : null);
    }
    setModels([]);
  }, [kind, profileName, profiles]);

  const payload = () => ({ name: profileName, kind, provider, model, endpoint, secret_reference: secretReference === "configured" ? undefined : secretReference, timeout_seconds: 300, maximum_retries: 1, maximum_concurrency: 1, daily_unit_limit: 1000000, capabilities, routing_priority: provider === "lm_studio" ? 30 : 10 });
  const changeProvider = (value: "lm_studio" | "openai" | "claude") => {
    setProvider(value);
    setModels([]);
    setSecretReference(null);
    setApiKey("");
    if (value === "openai") {
      setEndpoint("https://api.openai.com/v1");
      setModel(kind === "llm" ? "gpt-4.1-mini" : "text-embedding-3-small");
    } else if (value === "claude") {
      setEndpoint("https://api.anthropic.com/v1");
      setModel("claude-sonnet-4-5");
    } else {
      setEndpoint("http://host.docker.internal:1234/v1");
      setModel(kind === "llm" ? "qwen3-vl-8b-instruct" : "text-embedding-nomic-embed-text-v1.5");
    }
  };
  const saveCredential = async () => {
    if (!apiKey.trim()) return;
    setStatus("جاري تشفير المفتاح…");
    try {
      const response = await request<{ secret_reference: string }>("/api/v1/ai/credentials", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ provider, api_key: apiKey }) });
      setSecretReference(response.secret_reference);
      setApiKey("");
      setStatus("تم حفظ المفتاح مشفرًا. لا يمكن عرضه مرة أخرى.");
    } catch { setStatus("تعذر حفظ المفتاح الآمن."); }
  };
  const discover = async () => {
    setStatus(`جاري الاتصال بـ ${provider === "claude" ? "Claude" : provider === "openai" ? "OpenAI" : "LM Studio"}…`);
    try {
      const health = await request<AIHealth>("/api/v1/ai/profiles/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload()) });
      setModels(health.models); setStatus(health.healthy ? `متصل خلال ${health.latency_ms}ms — اختر الموديل` : `غير متصل: ${health.error_code}`);
    } catch { setStatus("تعذر الاتصال بالمزوّد أو أن المفتاح/الموديل غير متاح."); }
  };
  const activate = async () => {
    setStatus("جاري التحقق والتفعيل…");
    try {
      await request(`/api/v1/ai/profiles/${profileName}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload()) });
      await refresh(); setStatus(`تم تفعيل ${model}. الشات يستخدمه الآن.`);
    } catch { setStatus("لم يتم التفعيل: الموديل غير محمّل أو غير متاح."); }
  };
  const disableProfile = async (name: string) => {
    setStatus(`جاري تعطيل ${name}…`);
    try {
      await request(`/api/v1/ai/profiles/${name}/disable`, { method: "POST" });
      await refresh();
      setStatus(`تم تعطيل ${name}. سيستخدم النظام المزوّد المتاح التالي تلقائيًا.`);
    } catch { setStatus("تعذر تعطيل المزوّد."); }
  };
  const runTest = async () => {
    setResult(""); setStatus("جاري تنفيذ الاختبار الحقيقي…");
    try {
      if (kind === "llm") {
        const response = await request<{ text: string }>("/api/v1/ai/test/llm", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: testText }) });
        setResult(response.text);
      } else {
        const response = await request<{ model: string; embedding_space_id: string; dimensions: number; preview: number[] }>("/api/v1/ai/test/embedding", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: testText }) });
        setResult(`${response.model}\nSpace: ${response.embedding_space_id}\nDimensions: ${response.dimensions}\nPreview: ${response.preview.join(", ")}`);
      }
      setStatus("نجح الاختبار الحقيقي.");
    } catch { setStatus("فشل الاختبار. راجع تحميل الموديل المختار في LM Studio."); }
  };

  return <div className="ai-settings">
    <div className="settings-tabs"><button className={kind === "llm" ? "active" : ""} onClick={() => setKind("llm")}>LLM Bank</button><button className={kind === "embedding" ? "active" : ""} onClick={() => setKind("embedding")}>Embedding Bank</button></div>
    <div className="cloud-slot-grid">
      <button className={provider === "openai" ? "cloud-slot active" : "cloud-slot"} onClick={() => changeProvider("openai")}><strong>OpenAI API</strong><span>مفضل للعروض والمخرجات المرئية</span><small>{profiles.some((item) => item.provider === "openai" && item.status === "enabled") ? "مفعّل" : "غير مضاف"}</small></button>
      <button className={provider === "claude" ? "cloud-slot active" : "cloud-slot"} onClick={() => changeProvider("claude")}><strong>Claude API</strong><span>مفضل لتحليل الملفات والتقارير</span><small>{profiles.some((item) => item.provider === "claude" && item.status === "enabled") ? "مفعّل" : "غير مضاف"}</small></button>
      <button className="cloud-slot provider-planned" type="button" disabled aria-describedby="gamma-provider-note"><strong>Gamma API</strong><span>مخطط: إنشاء عروض تقديمية مرئية</span><small>غير مفعّل — لا يتم إرسال أي بيانات</small></button>
    </div>
    <p className="settings-note" id="gamma-provider-note">Gamma معروض كموفّر مستقبلي فقط. لا يوجد اتصال API أو إرسال بيانات أو تفعيل توجيه حتى اعتماد واجهته وتخزين أسراره وصلاحياته.</p>
    <div className="provider-status"><i /> <strong>{provider === "lm_studio" ? "LM Studio محلي" : provider === "openai" ? "OpenAI Cloud" : "Claude Cloud"}</strong><span>{status}</span></div>
    <label>المزوّد<select value={provider} onChange={(event) => changeProvider(event.target.value as "lm_studio" | "openai" | "claude")} dir="ltr"><option value="lm_studio">LM Studio (Local)</option><option value="openai">OpenAI</option><option value="claude">Claude (Anthropic)</option></select></label>
    {provider !== "lm_studio" && <><label>{provider === "claude" ? "Claude API key" : "OpenAI API key"}<input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={provider === "claude" ? "sk-ant-…" : "sk-…"} dir="ltr" autoComplete="new-password" /></label><button className="settings-action secondary" onClick={() => void saveCredential()} disabled={!apiKey.trim()}>حفظ المفتاح بأمان</button><p className="settings-note">لكل مزود مفتاح write-only مستقل ومشفّر؛ لا يعود إلى المتصفح بعد الحفظ.</p></>}
    <label>Endpoint<input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} dir="ltr" disabled={provider !== "lm_studio"} /></label>
    <p className="settings-note">المحلي هو الافتراضي الآن. بعد حفظ مفتاح OpenAI أو Claude وتفعيل موديله، يصبح السحابي أولوية للشات والـPlanner والوكلاء حسب المهمة؛ وعند غيابه أو فشله يعود للمحلي. السحابي مقيد افتراضيًا ببيانات public/internal؛ confidential/restricted تبقى محلية. التغيير يسري على الطلب التالي.</p>
    <button className="settings-action secondary" onClick={() => void discover()}>اكتشاف الموديلات واختبار الاتصال</button>
    <label>الموديل<select value={model} onChange={(event) => { setModel(event.target.value); setStatus(`تم اختيار ${event.target.value} — اضغط حفظ وتفعيل`); }} dir="ltr"><option value={model}>{model}</option>{models.filter((item) => item !== model).map((item) => <option key={item}>{item}</option>)}</select></label>
    <button className="settings-action" onClick={() => void activate()}>حفظ وتفعيل {kind === "llm" ? "LLM" : "Embedding"}</button>
    <div className="active-profiles">{profiles.filter((item) => item.kind === kind).map((item) => <div key={item.name}><strong>{item.name}</strong><span>{item.model} · v{item.version} · {item.status} · أولوية {item.routing_priority}</span>{item.status === "enabled" && <button type="button" onClick={() => void disableProfile(item.name)}>تعطيل</button>}</div>)}</div>
    <label>Playground<textarea value={testText} onChange={(event) => setTestText(event.target.value)} rows={3} /></label>
    <button className="settings-action test" onClick={() => void runTest()}>تشغيل اختبار حقيقي</button>
    {result && <pre className="ai-result">{result}</pre>}
    <div className="agents-summary"><div><strong>الوكلاء العاملون والمتاحون لك</strong><span>{agents.length} حسب الصلاحيات والتشغيل الفعلي</span></div><div className="agent-chips">{agents.map((agent) => <span key={agent.code} title={`${agent.category} · ${agent.capabilities.join(", ")} · ${agent.allowed_actions.join(", ")}`}>{agent.name} · {agent.category} · {agent.allowed_actions.includes("execute") ? "تنفيذ" : "قراءة/مسودة"}</span>)}</div></div>
  </div>;
}

function IntegrationForm({ request, onCreated }: {
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
  onCreated: () => Promise<void>;
}) {
  const [provider, setProvider] = useState<"jira" | "slack">("jira");
  const [name, setName] = useState("");
  const [authorization, setAuthorization] = useState("");
  const [scope, setScope] = useState<"organization" | "personal">("organization");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const endpoint = provider === "jira" ? "https://mcp.atlassian.com/v2/mcp?tools=all" : "https://mcp.slack.com/mcp";

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await request("/api/v1/integrations/connections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, name, endpoint_url: endpoint, authorization, scope }),
      });
      setName("");
      setAuthorization("");
      await onCreated();
    } finally {
      setSaving(false);
    }
  };

  const connect = async () => {
    if (!name.trim()) {
      setFormError("اكتب اسمًا للاتصال أولًا.");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const response = await request<{ authorization_url: string }>(`/api/v1/integrations/oauth/${provider}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, scope }),
      });
      window.location.assign(response.authorization_url);
    } catch (error) {
      setFormError(error instanceof Error ? "تعذر بدء OAuth. راجع إعداد التطبيق وصلاحيات المؤسسة." : "تعذر بدء OAuth.");
      setSaving(false);
    }
  };

  return (
    <form className="integration-form" onSubmit={(event) => void save(event)}>
      <select value={provider} onChange={(event) => setProvider(event.target.value as "jira" | "slack")} aria-label="مزود التكامل">
        <option value="jira">Jira / Atlassian</option><option value="slack">Slack</option>
      </select>
      <input value={name} onChange={(event) => setName(event.target.value)} placeholder="اسم الاتصال" required maxLength={120} />
      <select value={scope} onChange={(event) => setScope(event.target.value as "organization" | "personal")} aria-label="نطاق الاتصال">
        <option value="organization">كل المؤسسة</option><option value="personal">حسابي فقط</option>
      </select>
      <button className="upload-wide oauth-connect" type="button" onClick={() => void connect()} disabled={saving}>
        {saving ? "جاري التحويل…" : `ربط ${provider === "jira" ? "Jira" : "Slack"} بأمان`}
      </button>
      {formError && <span className="integration-error">{formError}</span>}
      <details className="manual-token">
        <summary>إعداد متقدم: API token أو حساب خدمة</summary>
        <input value={authorization} onChange={(event) => setAuthorization(event.target.value)} placeholder="Bearer … أو Basic …" type="password" autoComplete="off" />
        <button className="upload-wide" disabled={saving || !authorization.trim()}>{saving ? "جاري الحفظ…" : "إضافة بيانات الاعتماد يدويًا"}</button>
      </details>
    </form>
  );
}

function IntegrationCard({ connection, request, refresh }: {
  connection: IntegrationConnection;
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
  refresh: () => Promise<void>;
}) {
  const [result, setResult] = useState<string | null>(null);
  const [grants, setGrants] = useState<ConnectionGrant[]>([]);
  const [subjectType, setSubjectType] = useState("organization");
  const [subjectId, setSubjectId] = useState(connection.organization_id);
  const [toolName, setToolName] = useState("*");
  const [permission, setPermission] = useState("read");
  const [replacementCredential, setReplacementCredential] = useState("");
  const loadGrants = useCallback(async () => {
    setGrants(await request<ConnectionGrant[]>(`/api/v1/integrations/connections/${connection.id}/grants`));
  }, [connection.id, request]);
  useEffect(() => { void loadGrants().catch(() => setGrants([])); }, [loadGrants]);
  const verify = async () => {
    setResult("جاري الاختبار…");
    try {
      const response = await request<{ tool_count: number }>(`/api/v1/integrations/connections/${connection.id}/verify`, { method: "POST" });
      setResult(`متصل — ${response.tool_count} أداة`);
    } catch { setResult("فشل الاتصال"); }
  };
  const disable = async () => {
    if (!window.confirm(`تعطيل اتصال ${connection.name}؟ سيتم حذف بيانات الاعتماد المشفرة.`)) return;
    await request(`/api/v1/integrations/connections/${connection.id}`, { method: "DELETE" });
    await refresh();
  };
  const saveGrant = async () => {
    await request(`/api/v1/integrations/connections/${connection.id}/grants`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject_type: subjectType, subject_id: subjectId, tool_name: toolName, permission }),
    });
    await loadGrants();
  };
  const revoke = async () => {
    if (!window.confirm(`إلغاء اتصال ${connection.name} نهائيًا ومسح بياناته؟`)) return;
    await request(`/api/v1/integrations/connections/${connection.id}/revoke`, { method: "POST" });
    await refresh();
  };
  const reconnect = async () => {
    await request(`/api/v1/integrations/connections/${connection.id}/credential`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ authorization: replacementCredential }),
    });
    setReplacementCredential(""); await refresh();
  };
  return (
    <div className="integration-card">
      <div><strong>{connection.name}</strong><small>{connection.provider.toUpperCase()} · {connection.scope === "organization" ? "المؤسسة" : "شخصي"}</small></div>
      {result && <span>{result}</span>}
      {connection.status === "active" && <div><button onClick={() => void verify()}>اختبار</button><button onClick={() => void disable()}>تعطيل</button><button onClick={() => void revoke()}>إلغاء وربط</button></div>}
      {connection.status === "active" && <details className="grant-editor">
        <summary>صلاحيات الأدوات</summary>
        <select value={subjectType} onChange={(event) => { const value = event.target.value; setSubjectType(value); if (value === "organization") setSubjectId(connection.organization_id); }}>
          <option value="organization">المؤسسة</option><option value="department">قسم</option><option value="team">فريق</option><option value="project">مشروع</option><option value="agent">Agent</option><option value="user">موظف</option>
        </select>
        <input value={subjectId} onChange={(event) => setSubjectId(event.target.value)} placeholder="معرّف النطاق" />
        <input value={toolName} onChange={(event) => setToolName(event.target.value)} placeholder="اسم الأداة أو *" />
        <select value={permission} onChange={(event) => setPermission(event.target.value)}><option value="read">قراءة</option><option value="draft">مسودة</option><option value="execute">تنفيذ</option><option value="administer">إدارة</option></select>
        <button onClick={() => void saveGrant()}>حفظ الصلاحية</button>
        <div className="grant-list">{grants.map((grant) => <small key={grant.id}>{grant.subject_type}:{grant.subject_id} · {grant.tool_name} · {grant.permission}</small>)}</div>
      </details>}
      {connection.status !== "active" && <div className="reconnect-form"><input type="password" value={replacementCredential} onChange={(event) => setReplacementCredential(event.target.value)} placeholder="بيانات اعتماد جديدة" /><button disabled={!replacementCredential.trim()} onClick={() => void reconnect()}>إعادة الاتصال</button></div>}
    </div>
  );
}

function ChatMessage({ message }: { message: Message }) {
  const assistant = message.role === "assistant";
  const artifactMatch = assistant
    ? message.content.match(/\[artifact:([0-9a-f-]{36}):v(\d+)\]/i)
    : null;
  const visibleContent = artifactMatch
    ? message.content.replace(artifactMatch[0], "").trim()
    : message.content;
  return (
    <article className={`message ${assistant ? "assistant-message" : "user-message"}`}>
      <span className={`avatar ${assistant ? "agent" : "user"}`}>{assistant ? "T" : "أ"}</span>
      <div className="message-body">
        <strong className="message-name">{assistant ? "Tactiqo" : "أنت"}</strong>
        <p>{visibleContent}</p>
        {artifactMatch && (
          <div className="chat-artifact">
            <strong>الملف الناتج · نسخة {artifactMatch[2]}</strong>
            <a href={`${API_BASE_URL}/api/v1/artifacts/${artifactMatch[1]}/versions/${artifactMatch[2]}/download`} download>تنزيل الملف</a>
          </div>
        )}
      </div>
    </article>
  );
}

function Thinking({ label }: { label: string }) {
  return <div className="thinking"><span /><span /><span /><em>{label}</em></div>;
}

function ApprovalCard({ approval, onDecide }: { approval: Approval; onDecide: (decision: "approved" | "rejected") => Promise<void> }) {
  return (
    <section className="approval-card">
      <div className="approval-icon">!</div>
      <div><strong>هذه الخطوة تحتاج موافقتك</strong><p>الوكيل يريد تشغيل <code>{approval.tool_name}</code>. لن يتم أي تغيير قبل اختيارك.</p><pre>{JSON.stringify(approval.arguments, null, 2)}</pre>
        <div className="approval-actions"><button className="approve" onClick={() => void onDecide("approved")}>موافقة وتشغيل</button><button onClick={() => void onDecide("rejected")}>رفض</button></div>
      </div>
    </section>
  );
}

function documentStatus(document: { status: string; error_code?: string | null }) {
  if (document.error_code === "derived_index_unavailable") return "جاهز محليًا — الفهرس الخارجي متعطل";
  return ({ uploaded: "في قائمة المعالجة", processing: "جاري التحليل", ready: "جاهز للبحث", failed: "فشلت المعالجة", revoked: "تم إلغاء المصدر" } as Record<string, string>)[document.status] ?? "حالة غير معروفة";
}
