"use client";

import { ChangeEvent, FormEvent, useCallback, useEffect, useRef, useState } from "react";

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
  status: "uploaded" | "processing" | "ready" | "failed";
  parser_name: string | null;
  error_code: string | null;
};

type Approval = {
  approval_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
};

type Citation = {
  citation_id: string;
  title: string;
  locator: Record<string, unknown>;
};

const suggestions = [
  { icon: "◫", title: "حالة المشروع", prompt: "اعرض لي حالة المشروع الحالية وأهم نقاط المتابعة" },
  { icon: "↗", title: "البنود المتأخرة", prompt: "ما هي البنود المتأخرة في المشروع؟" },
  { icon: "✓", title: "مهمة متابعة", prompt: "أنشئ مهمة متابعة لمراجعة فلو الموافقات" },
] as const;

export default function HomePage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [runStep, setRunStep] = useState<string | null>(null);
  const [streamedAnswer, setStreamedAnswer] = useState("");
  const [approval, setApproval] = useState<Approval | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const endOfMessages = useRef<HTMLDivElement>(null);

  const request = useCallback(async <T,>(path: string, init?: RequestInit): Promise<T> => {
    const response = await fetch(`${API_BASE_URL}${path}`, init);
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `Request failed (${response.status})`);
    }
    return response.json() as Promise<T>;
  }, []);

  const refreshConversations = useCallback(async () => {
    const items = await request<Conversation[]>("/api/v1/conversations");
    setConversations(items);
  }, [request]);

  const refreshDocuments = useCallback(async () => {
    const items = await request<KnowledgeDocument[]>("/api/v1/knowledge/documents");
    setDocuments(items);
  }, [request]);

  useEffect(() => {
    void Promise.all([refreshConversations(), refreshDocuments()]).catch(() => {
      setNotice("تعذر الاتصال بالخادم. تأكد أن خدمات Tactiqo تعمل.");
    });
  }, [refreshConversations, refreshDocuments]);

  useEffect(() => {
    endOfMessages.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streamedAnswer, approval, runStep]);

  const openConversation = async (id: string) => {
    if (busy) return;
    setConversationId(id);
    setMessages(await request<Message[]>(`/api/v1/conversations/${id}/messages`));
    setStreamedAnswer("");
    setApproval(null);
    setCitations([]);
    setSidebarOpen(false);
  };

  const newChat = () => {
    if (busy) return;
    setConversationId(null);
    setMessages([]);
    setStreamedAnswer("");
    setApproval(null);
    setCitations([]);
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
      const data = JSON.parse((event as MessageEvent).data) as { step: string };
      setRunStep(data.step);
    });
    stream.addEventListener("retrieval.completed", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as { citations: Citation[] };
      setCitations(data.citations ?? []);
      setRunStep("retrieval");
    });
    stream.addEventListener("tool.call", () => setRunStep("tool"));
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
    setApproval(null);
    setCitations([]);
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

  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setNotice(`جاري رفع ${file.name}…`);
    const form = new FormData();
    form.append("file", file);
    try {
      await request("/api/v1/knowledge/documents", { method: "POST", body: form });
      setNotice("تم رفع المستند، وبدأت معالجته وإضافته للمعرفة.");
      setKnowledgeOpen(true);
      await refreshDocuments();
      window.setTimeout(() => void refreshDocuments(), 1800);
    } catch {
      setNotice("تعذر رفع المستند. الحد الأقصى 20MB.");
    }
  };

  const stepLabel: Record<string, string> = {
    queued: "جاري بدء الوكيل",
    guardrails: "فحص الحماية",
    retrieval: "البحث في المعرفة",
    planning: "تخطيط الخطوات",
    tool: "تشغيل الأداة",
    approval: "بانتظار موافقتك",
    responding: "صياغة الإجابة",
    cancelling: "جاري الإلغاء",
  };

  return (
    <main className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark">T</div>
          <div><strong>Tactiqo</strong><span>AI Operations</span></div>
          <button className="icon-button mobile-only" onClick={() => setSidebarOpen(false)} aria-label="إغلاق القائمة">×</button>
        </div>
        <button className="new-chat" onClick={newChat}><span>＋</span> محادثة جديدة</button>
        <p className="sidebar-label">المحادثات</p>
        <nav className="conversation-list" aria-label="المحادثات السابقة">
          {conversations.length === 0 && <span className="empty-list">لا توجد محادثات بعد</span>}
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
          <div className="security-row"><span>◈</span><div><strong>وضع مؤسسي آمن</strong><small>الموافقات والتدقيق مفعّلان</small></div></div>
          <div className="profile"><span className="avatar small">أ</span><div><strong>Ahmed</strong><small>مساحة العمل المحلية</small></div><span>•••</span></div>
        </div>
      </aside>

      {sidebarOpen && <button className="scrim" onClick={() => setSidebarOpen(false)} aria-label="إغلاق القائمة" />}

      <section className="workspace">
        <header className="topbar">
          <button className="icon-button menu-button" onClick={() => setSidebarOpen(true)} aria-label="فتح القائمة">☰</button>
          <button className="model-select">Tactiqo Agent <span>⌄</span></button>
          <div className="top-actions">
            <span className="live-badge"><i /> النظام متصل</span>
            <button className="knowledge-button" onClick={() => setKnowledgeOpen((value) => !value)}>▱ <span>المعرفة</span></button>
          </div>
        </header>

        <div className="chat-scroll">
          {messages.length === 0 && !busy ? (
            <section className="welcome">
              <div className="welcome-mark">T</div>
              <h1>كيف أقدر أساعدك اليوم؟</h1>
              <p>اسأل عن مشاريعك، حلّل مستندًا، أو شغّل أداة. كل إجراء مؤثر يحتاج موافقتك أولًا.</p>
              <div className="suggestion-grid">
                {suggestions.map((item) => (
                  <button key={item.title} onClick={() => setInput(item.prompt)}>
                    <span>{item.icon}</span><strong>{item.title}</strong><small>{item.prompt}</small>
                  </button>
                ))}
              </div>
            </section>
          ) : (
            <div className="message-thread">
              {messages.map((message) => <ChatMessage key={message.id} message={message} />)}
              {(busy || streamedAnswer) && (
                <article className="message assistant-message">
                  <span className="avatar agent">T</span>
                  <div className="message-body">
                    <strong className="message-name">Tactiqo</strong>
                    {streamedAnswer ? <p>{streamedAnswer}</p> : <Thinking label={stepLabel[runStep ?? "queued"]} />}
                    {citations.length > 0 && (
                      <div className="citations">
                        <span>المصادر</span>
                        {citations.map((citation, index) => <button key={citation.citation_id}>[{index + 1}] {citation.title}</button>)}
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
              placeholder="اكتب رسالتك إلى Tactiqo…"
              rows={1}
              disabled={busy}
              aria-label="رسالتك"
            />
            <div className="composer-actions">
              <input ref={fileInput} type="file" hidden onChange={(event) => void upload(event)} accept=".pdf,.docx,.xlsx,.csv,.txt,.md" />
              <button type="button" className="attach" onClick={() => fileInput.current?.click()} aria-label="إرفاق مستند">＋</button>
              <span className="composer-hint">يدعم المستندات والجداول حتى 20MB</span>
              <button type="submit" className="send" disabled={!input.trim() || busy} aria-label="إرسال">↑</button>
            </div>
          </form>
          <small className="disclaimer">قد يخطئ الذكاء الاصطناعي. راجع النتائج المهمة قبل الاعتماد عليها.</small>
        </div>
      </section>

      <aside className={`knowledge-drawer ${knowledgeOpen ? "drawer-open" : ""}`}>
        <div className="drawer-header"><div><small>RAG KNOWLEDGE</small><h2>مصادر المعرفة</h2></div><button onClick={() => setKnowledgeOpen(false)}>×</button></div>
        <p>المستندات الأصلية محفوظة في MinIO، والنص المنظم وحالته في PostgreSQL.</p>
        <button className="upload-wide" onClick={() => fileInput.current?.click()}>＋ رفع مستند جديد</button>
        <div className="document-list">
          {documents.length === 0 && <div className="document-empty">ارفع ملفًا لبدء بناء معرفة المشروع.</div>}
          {documents.map((document) => (
            <div className="document" key={document.id}>
              <span className="file-icon">▤</span><div><strong>{document.name}</strong><small><i className={`status-dot ${document.status}`} /> {documentStatus(document)}</small></div>
            </div>
          ))}
        </div>
      </aside>
    </main>
  );
}

function ChatMessage({ message }: { message: Message }) {
  const assistant = message.role === "assistant";
  return (
    <article className={`message ${assistant ? "assistant-message" : "user-message"}`}>
      <span className={`avatar ${assistant ? "agent" : "user"}`}>{assistant ? "T" : "أ"}</span>
      <div className="message-body"><strong className="message-name">{assistant ? "Tactiqo" : "أنت"}</strong><p>{message.content}</p></div>
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

function documentStatus(document: KnowledgeDocument) {
  if (document.error_code === "derived_index_unavailable") return "جاهز محليًا — الفهرس الخارجي متعطل";
  return { uploaded: "في قائمة المعالجة", processing: "جاري التحليل", ready: "جاهز للبحث", failed: "فشلت المعالجة" }[document.status];
}
