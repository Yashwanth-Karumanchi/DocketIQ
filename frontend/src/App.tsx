import { useEffect, useMemo, useState } from "react";
import "./App.css";

type User = {
  id: string;
  email: string;
  fullName: string;
  avatarUrl: string;
  role: string;
};

type CaseItem = {
  id: string;
  case_number: string;
  title: string;
  status: string;
  priority: string;
  summary: string | null;
  client_name: string;
  client_email?: string | null;
  client_phone?: string | null;
  claim_number: string | null;
  insurance_company: string | null;
  document_count?: number;
  open_task_count?: number;
  pending_action_count?: number;
};

type DocumentItem = {
  id: string;
  file_name: string;
  status: string;
  text_char_count: number;
  created_at: string;
};

type TimelineEvent = {
  id: string;
  event_date: string;
  event_type: string;
  title: string;
  description: string | null;
  source: string | null;
};

type CaseTask = {
  id: string;
  title: string;
  description: string | null;
  status: string;
  priority: string;
  due_date: string | null;
  created_at: string;
};

type PendingAction = {
  id: string;
  type: string;
  preview: string;
};

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  pendingAction?: PendingAction;
};

type DashboardData = {
  stats: {
    totalCases: number;
    highPriority: number;
    openTasks: number;
    pendingActions: number;
    documentCount: number;
  };
  cases: CaseItem[];
  calendarEvents: any[];
  pendingActions: any[];
  recentActivity: any[];
};

type GraphData = {
  nodes: any[];
  edges: any[];
};

type AgentResult = {
  title: string;
  subtitle: string;
  payload: any;
};

type DashboardFilter =
  | "all"
  | "highPriority"
  | "openTasks"
  | "pendingActions"
  | "documents";

const navItems = ["Dashboard", "Cases", "New Case", "Calendar", "Reports"];

function formatDate(value?: string | null) {
  if (!value) return "Not available";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatShortDate(value?: string | null) {
  if (!value) return "Unknown date";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function normalizeSearch(value: any) {
  return String(value ?? "").toLowerCase().trim();
}

function includesSearch(searchText: string, values: any[]) {
  const query = normalizeSearch(searchText);
  if (!query) return true;
  return values.some((value) => normalizeSearch(value).includes(query));
}

function caseMatchesSearch(caseItem: CaseItem, searchText: string) {
  return includesSearch(searchText, [
    caseItem.case_number,
    caseItem.title,
    caseItem.status,
    caseItem.priority,
    caseItem.summary,
    caseItem.client_name,
    caseItem.client_email,
    caseItem.client_phone,
    caseItem.claim_number,
    caseItem.insurance_company,
    caseItem.document_count,
    caseItem.open_task_count,
    caseItem.pending_action_count,
  ]);
}

function calendarEventMatchesSearch(event: any, searchText: string) {
  return includesSearch(searchText, [
    event.id,
    event.title,
    event.summary,
    event.description,
    event.start_time,
    event.end_time,
    event.source,
    event.google_event_link,
  ]);
}

function agentRunMatchesSearch(run: any, searchText: string) {
  return includesSearch(searchText, [
    run.agent_name,
    run.status,
    run.result_summary,
    run.case_number,
    run.case_title,
    run.client_name,
    run.created_at,
  ]);
}

function reportMatchesSearch(report: any, searchText: string) {
  return includesSearch(searchText, [
    report.title,
    report.report_type,
    report.case_number,
    report.case_title,
    report.client_name,
    report.summary,
    report.created_at,
  ]);
}

function stringifyReport(data: any) {
  if (!data) return "";
  if (typeof data === "string") return data;

  const lines: string[] = [];

  const push = (label: string, value: any) => {
    if (value === undefined || value === null || value === "") return;

    if (Array.isArray(value)) {
      lines.push(`\n${label}:`);

      if (!value.length) {
        lines.push("- None identified.");
        return;
      }

      value.forEach((item) => {
        if (typeof item === "string") {
          lines.push(`- ${item}`);
          return;
        }

        const title =
          item.title ||
          item.item ||
          item.gap ||
          item.fact ||
          item.relationshipType ||
          "Item";

        const detail =
          item.reason ||
          item.explanation ||
          item.description ||
          item.recommendedAction ||
          item.whyItMatters ||
          item.impact ||
          item.evidence ||
          "";

        lines.push(`- ${title}${detail ? `: ${detail}` : ""}`);
      });

      return;
    }

    if (typeof value === "object") {
      lines.push(`\n${label}: ${JSON.stringify(value, null, 2)}`);
      return;
    }

    lines.push(`\n${label}: ${value}`);
  };

  push("Executive Summary", data.executiveSummary || data.summary || data.resultSummary);
  push("Readiness Score", data.readinessScore);
  push("Handoff Status", data.handoffStatus);
  push("Consistency Score", data.consistencyScore);
  push("Timeline Completeness", data.timelineCompleteness);
  push("Missing Items", data.missingItems);
  push("Present Items", data.presentItems);
  push("Risk Flags", data.riskFlags);
  push("Events", data.events);
  push("Timeline Gaps", data.timelineGaps || data.gaps);
  push("Strengths", data.strengths);
  push("Blockers", data.blockers);
  push("Contradictions", data.contradictions);
  push("Uncertainty Items", data.uncertaintyItems);
  push(
    "Top Actions",
    data.topActions || data.nextOperationalSteps || data.nextSteps || data.recommendedActions
  );
  push("Relationships", data.relationships);
  push("Limitations", data.limitations);

  return lines.join("\n").trim();
}

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [activeView, setActiveView] = useState("Dashboard");
  const [dashboardFilter, setDashboardFilter] = useState<DashboardFilter>("all");

  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [selectedCase, setSelectedCase] = useState<CaseItem | null>(null);

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [timelineEvents, setTimelineEvents] = useState<TimelineEvent[]>([]);
  const [caseTasks, setCaseTasks] = useState<CaseTask[]>([]);
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] });
  const [suggestions, setSuggestions] = useState<any[]>([]);

  const [agentRuns, setAgentRuns] = useState<any[]>([]);
  const [allAgentRuns, setAllAgentRuns] = useState<any[]>([]);
  const [allReports, setAllReports] = useState<any[]>([]);

  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [agentResult, setAgentResult] = useState<AgentResult | null>(null);

  const [expandedTimelineItem, setExpandedTimelineItem] = useState<string | null>(null);
  const [expandedTask, setExpandedTask] = useState<string | null>(null);
  const [expandedSuggestion, setExpandedSuggestion] = useState<string | null>(null);

  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    missingItems: true,
    documents: false,
    timeline: false,
    agents: false,
    autopilot: true,
    graph: false,
    reports: false,
  });

  const [isUploading, setIsUploading] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [isRunningAgent, setIsRunningAgent] = useState(false);

  const [isChatMounted, setIsChatMounted] = useState(false);
  const [isChatClosing, setIsChatClosing] = useState(false);

  const [liveCalendarEvents, setLiveCalendarEvents] = useState<any[]>([]);
  const [calendarSyncedAt, setCalendarSyncedAt] = useState<string | null>(null);
  const [hasSyncedCalendar, setHasSyncedCalendar] = useState(false);

  const [lastAutopilotAt, setLastAutopilotAt] = useState<string | null>(null);
  const [isAutopilotSyncing, setIsAutopilotSyncing] = useState(false);

  const [dashboardSearch, setDashboardSearch] = useState("");
  const [casesSearch, setCasesSearch] = useState("");
  const [calendarSearch, setCalendarSearch] = useState("");
  const [reportsSearch, setReportsSearch] = useState("");

  const [intakeForm, setIntakeForm] = useState({
    clientName: "",
    clientEmail: "",
    clientPhone: "",
    preferredLanguage: "English",
    caseType: "Personal Injury",
    incidentDate: "",
    incidentType: "",
    incidentLocation: "",
    insuranceCompany: "",
    claimNumber: "",
    priority: "Medium",
    intakeNotes: "",
  });

  const [isCreatingCase, setIsCreatingCase] = useState(false);

  const activeCaseSummary = useMemo(() => {
    if (!selectedCase) return "No case selected";
    return `${selectedCase.case_number} · ${selectedCase.client_name}`;
  }, [selectedCase]);

  const calendarEvents = useMemo(() => {
    if (hasSyncedCalendar) return liveCalendarEvents;
    return dashboardData?.calendarEvents || [];
  }, [hasSyncedCalendar, liveCalendarEvents, dashboardData]);

  const filteredCalendarEvents = useMemo(() => {
    return calendarEvents.filter((event) =>
      calendarEventMatchesSearch(event, calendarSearch)
    );
  }, [calendarEvents, calendarSearch]);

  const missingItemTasks = useMemo(() => {
    return caseTasks.filter((task) => {
      const title = task.title.toLowerCase();

      return (
        title.includes("missing") ||
        title.includes("readiness blocker") ||
        title.includes("next best action") ||
        title.includes("consistency check")
      );
    });
  }, [caseTasks]);

  const dashboardCases = useMemo(() => {
    let filteredCases = cases;

    if (dashboardFilter === "highPriority") {
      filteredCases = filteredCases.filter((caseItem) => caseItem.priority === "High");
    }

    if (dashboardFilter === "openTasks") {
      filteredCases = filteredCases.filter(
        (caseItem) => Number(caseItem.open_task_count || 0) > 0
      );
    }

    if (dashboardFilter === "pendingActions") {
      filteredCases = filteredCases.filter(
        (caseItem) => Number(caseItem.pending_action_count || 0) > 0
      );
    }

    if (dashboardFilter === "documents") {
      filteredCases = filteredCases.filter(
        (caseItem) => Number(caseItem.document_count || 0) > 0
      );
    }

    return filteredCases.filter((caseItem) =>
      caseMatchesSearch(caseItem, dashboardSearch)
    );
  }, [cases, dashboardFilter, dashboardSearch]);

  const filteredCases = useMemo(() => {
    return cases.filter((caseItem) => caseMatchesSearch(caseItem, casesSearch));
  }, [cases, casesSearch]);

  const filteredAgentRuns = useMemo(() => {
    return allAgentRuns.filter((run) => agentRunMatchesSearch(run, reportsSearch));
  }, [allAgentRuns, reportsSearch]);

  const filteredReports = useMemo(() => {
    return allReports.filter((report) => reportMatchesSearch(report, reportsSearch));
  }, [allReports, reportsSearch]);

  const login = () => {
    window.location.href = "/api/auth/google/start";
  };

  const logout = async () => {
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "include",
    });

    setUser(null);
    setDashboardData(null);
    setCases([]);
    setSelectedCase(null);
    setDocuments([]);
    setTimelineEvents([]);
    setCaseTasks([]);
    setGraphData({ nodes: [], edges: [] });
    setSuggestions([]);
    setChatMessages([]);
    setLiveCalendarEvents([]);
    setCalendarSyncedAt(null);
    setHasSyncedCalendar(false);
  };

  const loadAllReports = async () => {
    const res = await fetch("/api/dashboard/reports", {
      credentials: "include",
    });

    if (!res.ok) return;

    const data = await res.json();
    setAllAgentRuns(data.agentRuns || []);
    setAllReports(data.reports || []);
  };

  const loadDashboard = async () => {
    const res = await fetch("/api/dashboard", { credentials: "include" });
    if (!res.ok) return;

    const data = await res.json();
    setDashboardData(data);
    setCases(data.cases || []);
    await loadAllReports();
  };

  const loadDocuments = async (caseId: string) => {
    const res = await fetch(`/api/documents/cases/${caseId}`, {
      credentials: "include",
    });

    if (!res.ok) return;

    const data = await res.json();
    setDocuments(data.documents || []);
  };

  const loadTimeline = async (caseId: string) => {
    const res = await fetch(`/api/dashboard/cases/${caseId}/timeline`, {
      credentials: "include",
    });

    if (!res.ok) {
      setTimelineEvents([]);
      return;
    }

    const data = await res.json();
    setTimelineEvents(data.timeline || []);
  };

  const loadTasks = async (caseId: string) => {
    const res = await fetch(`/api/dashboard/cases/${caseId}/tasks`, {
      credentials: "include",
    });

    if (!res.ok) {
      setCaseTasks([]);
      return;
    }

    const data = await res.json();
    setCaseTasks(data.tasks || []);
  };

  const loadReports = async (caseId: string) => {
    const res = await fetch(`/api/dashboard/cases/${caseId}/reports`, {
      credentials: "include",
    });

    if (!res.ok) {
      setAgentRuns([]);
      return;
    }

    const data = await res.json();
    setAgentRuns(data.agentRuns || []);
  };

  const loadGraph = async (caseId: string) => {
    const res = await fetch(`/api/dashboard/cases/${caseId}/graph`, {
      credentials: "include",
    });

    if (!res.ok) {
      setGraphData({ nodes: [], edges: [] });
      return;
    }

    const data = await res.json();
    setGraphData(data);
  };

  const loadSuggestions = async (caseId: string) => {
    const res = await fetch(`/api/autopilot/cases/${caseId}/suggestions`, {
      credentials: "include",
    });

    if (!res.ok) {
      setSuggestions([]);
      return;
    }

    const data = await res.json();
    setSuggestions(data.suggestions || []);
  };

  const syncGoogleCalendar = async () => {
    const res = await fetch(`/api/calendar/upcoming?ts=${Date.now()}`, {
      credentials: "include",
      cache: "no-store",
    });

    if (!res.ok) return;

    const data = await res.json();
    setHasSyncedCalendar(true);
    setLiveCalendarEvents(data.events || []);
    setCalendarSyncedAt(data.syncedAt || null);
  };

  const refreshSelectedCaseData = async (caseId: string) => {
    await Promise.all([
      loadDocuments(caseId),
      loadTimeline(caseId),
      loadTasks(caseId),
      loadReports(caseId),
      loadGraph(caseId),
      loadSuggestions(caseId),
      loadDashboard(),
    ]);
  };

  const openChat = () => {
    setIsChatMounted(true);
    setIsChatClosing(false);
  };

  const closeChat = () => {
    setIsChatClosing(true);

    window.setTimeout(() => {
      setIsChatMounted(false);
      setIsChatClosing(false);
    }, 240);
  };

  const toggleChat = () => {
    if (isChatMounted && !isChatClosing) {
      closeChat();
      return;
    }

    openChat();
  };

  const openCaseWorkspace = async (caseItem: CaseItem) => {
    setSelectedCase(caseItem);
    setActiveView("Case Workspace");
    setAgentResult(null);
    setExpandedTimelineItem(null);
    setExpandedTask(null);
    setExpandedSuggestion(null);
    setChatMessages([]);
    await refreshSelectedCaseData(caseItem.id);
  };

  const updateIntakeField = (field: string, value: string) => {
    setIntakeForm((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const createIntakeCase = async () => {
    if (!intakeForm.clientName.trim() || !intakeForm.intakeNotes.trim()) {
      alert("Client name and intake notes are required.");
      return;
    }

    setIsCreatingCase(true);

    const res = await fetch("/api/intake/cases", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ...intakeForm,
        incidentDate: intakeForm.incidentDate || null,
        clientEmail: intakeForm.clientEmail || null,
        clientPhone: intakeForm.clientPhone || null,
        incidentType: intakeForm.incidentType || null,
        incidentLocation: intakeForm.incidentLocation || null,
        insuranceCompany: intakeForm.insuranceCompany || null,
        claimNumber: intakeForm.claimNumber || null,
      }),
    });

    setIsCreatingCase(false);

    if (!res.ok) {
      const error = await res.json().catch(() => null);
      alert(error?.detail || "Could not create case.");
      return;
    }

    const data = await res.json();

    setIntakeForm({
      clientName: "",
      clientEmail: "",
      clientPhone: "",
      preferredLanguage: "English",
      caseType: "Personal Injury",
      incidentDate: "",
      incidentType: "",
      incidentLocation: "",
      insuranceCompany: "",
      claimNumber: "",
      priority: "Medium",
      intakeNotes: "",
    });

    await loadDashboard();

    const newCaseRes = await fetch("/api/dashboard", {
      credentials: "include",
    });

    if (newCaseRes.ok) {
      const dashboard = await newCaseRes.json();
      const createdCase = (dashboard.cases || []).find(
        (caseItem: CaseItem) => caseItem.id === data.caseId
      );

      if (createdCase) {
        await openCaseWorkspace(createdCase);
        return;
      }
    }

    alert(`Created ${data.caseNumber}`);
    setActiveView("Cases");
  };

  useEffect(() => {
    fetch("/api/auth/me", { credentials: "include" })
      .then((res) => {
        if (!res.ok) return null;
        return res.json();
      })
      .then(async (data) => {
        setUser(data);
        if (data) await loadDashboard();
      })
      .catch(() => setUser(null));
  }, []);

  useEffect(() => {
    if (!user) return;

    syncGoogleCalendar();

    const intervalId = window.setInterval(() => {
      syncGoogleCalendar();
    }, 10000);

    return () => window.clearInterval(intervalId);
  }, [user]);

  useEffect(() => {
    if (!user || !selectedCase) return;

    const intervalId = window.setInterval(() => {
      refreshAutopilot(true);
    }, 30 * 60 * 1000);

    return () => window.clearInterval(intervalId);
  }, [user, selectedCase?.id]);

  const uploadDocument = async (file: File) => {
    if (!selectedCase) return;

    const formData = new FormData();
    formData.append("file", file);

    setIsUploading(true);

    const res = await fetch(`/api/documents/cases/${selectedCase.id}/upload`, {
      method: "POST",
      credentials: "include",
      body: formData,
    });

    setIsUploading(false);

    if (!res.ok) {
      const error = await res.json().catch(() => null);
      alert(error?.detail || "Upload failed");
      return;
    }

    await refreshSelectedCaseData(selectedCase.id);

    setAgentResult({
      title: "Document Added",
      subtitle:
        "The new document has been processed. Future chat and agent runs will use it automatically.",
      payload: {
        nextStep:
          "Run Missing Items, Timeline, Readiness, or ask the chat a follow-up question.",
      },
    });
  };

  const runLegalOpsAgent = async (
    label: string,
    endpoint: string,
    method: "POST" | "GET" = "POST"
  ) => {
    if (!selectedCase) return;

    setIsRunningAgent(true);
    setAgentResult(null);

    const res = await fetch(endpoint, {
      method,
      credentials: "include",
    });

    setIsRunningAgent(false);

    if (!res.ok) {
      const error = await res.json().catch(() => null);

      setAgentResult({
        title: `${label} failed`,
        subtitle: error?.detail || "The agent could not complete the request.",
        payload: {},
      });

      return;
    }

    if (endpoint.includes("handoff-report")) {
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");

      link.href = url;
      link.download = `docketiq_handoff_${selectedCase.case_number}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();

      window.URL.revokeObjectURL(url);

      setAgentResult({
        title: "Attorney Handoff Report",
        subtitle: "Report downloaded successfully.",
        payload: { nextStep: "Review the downloaded PDF." },
      });

      await refreshSelectedCaseData(selectedCase.id);
      return;
    }

    const data = await res.json();

    setAgentResult({
      title: data.reportTitle || label,
      subtitle:
        data.executiveSummary ||
        data.summary ||
        data.resultSummary ||
        "Agent run completed successfully.",
      payload: data,
    });

    await refreshSelectedCaseData(selectedCase.id);
  };

  const runMissingItems = () => {
    if (!selectedCase) return;
    runLegalOpsAgent(
      "Missing Items Review",
      `/api/legal-ops/cases/${selectedCase.id}/missing-items`
    );
  };

  const runTimeline = () => {
    if (!selectedCase) return;
    runLegalOpsAgent(
      "Case Timeline Review",
      `/api/legal-ops/cases/${selectedCase.id}/timeline`
    );
  };

  const runReadiness = () => {
    if (!selectedCase) return;
    runLegalOpsAgent(
      "Case Readiness Review",
      `/api/advanced-agents/cases/${selectedCase.id}/readiness`
    );
  };

  const runContradictions = () => {
    if (!selectedCase) return;
    runLegalOpsAgent(
      "Contradiction Review",
      `/api/advanced-agents/cases/${selectedCase.id}/contradictions`
    );
  };

  const runNextBestAction = () => {
    if (!selectedCase) return;
    runLegalOpsAgent(
      "Next Best Action Plan",
      `/api/advanced-agents/cases/${selectedCase.id}/next-best-actions`
    );
  };

  const runRelationshipAgent = () => {
    if (!selectedCase) return;
    runLegalOpsAgent(
      "Case Relationship Review",
      `/api/advanced-agents/cases/${selectedCase.id}/relationships`
    );
  };

  const downloadHandoffReport = () => {
    if (!selectedCase) return;
    runLegalOpsAgent(
      "Attorney Handoff Report",
      `/api/legal-ops/cases/${selectedCase.id}/handoff-report`,
      "GET"
    );
  };

  const refreshAutopilot = async (silent = false) => {
    if (!selectedCase) return;

    if (silent) {
      setIsAutopilotSyncing(true);
    } else {
      setIsRunningAgent(true);
    }

    const res = await fetch(`/api/autopilot/cases/${selectedCase.id}/refresh`, {
      method: "POST",
      credentials: "include",
    });

    setIsAutopilotSyncing(false);
    setIsRunningAgent(false);

    if (!res.ok) {
      if (!silent) alert("Autopilot refresh failed.");
      return;
    }

    const data = await res.json();
    setLastAutopilotAt(new Date().toISOString());

    if (!silent) {
      setAgentResult({
        title: "Communication Autopilot",
        subtitle: data.summary || "Autopilot created communication suggestions.",
        payload: data,
      });
    }

    await refreshSelectedCaseData(selectedCase.id);
  };

  const convertSuggestionToAction = async (suggestionId: string) => {
    const res = await fetch(
      `/api/autopilot/suggestions/${suggestionId}/convert-to-action`,
      {
        method: "POST",
        credentials: "include",
      }
    );

    if (!res.ok) {
      alert("Could not convert suggestion.");
      return;
    }

    alert("Suggestion converted to a pending email action.");

    if (selectedCase) {
      await refreshSelectedCaseData(selectedCase.id);
    }
  };

  const askQuestion = async () => {
    if (!question.trim()) return;

    const userQuestion = question.trim();
    setQuestion("");
    setChatMessages((prev) => [...prev, { role: "user", text: userQuestion }]);
    setIsThinking(true);

    const chatUrl = selectedCase
      ? `/api/rag/cases/${selectedCase.id}/chat`
      : "/api/rag/chat";

    const res = await fetch(chatUrl, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message: userQuestion }),
    });

    setIsThinking(false);

    if (!res.ok) {
      const error = await res.json().catch(() => null);

      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: error?.detail || "Something went wrong while answering.",
        },
      ]);

      return;
    }

    const data = await res.json();

    setChatMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        text: data.answer,
        pendingAction: data.pendingAction,
      },
    ]);

    if (selectedCase) {
      await refreshSelectedCaseData(selectedCase.id);
    } else {
      await loadDashboard();
    }
  };

  const confirmAction = async (actionId: string) => {
    const res = await fetch(`/api/actions/${actionId}/confirm`, {
      method: "POST",
      credentials: "include",
    });

    if (!res.ok) {
      const error = await res.json().catch(() => null);

      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: error?.detail?.message || error?.detail || "Action failed.",
        },
      ]);

      return;
    }

    const data = await res.json();

    setChatMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        text: data.message,
      },
    ]);

    if (selectedCase) await refreshSelectedCaseData(selectedCase.id);
  };

  const cancelAction = async (actionId: string) => {
    const res = await fetch(`/api/actions/${actionId}/cancel`, {
      method: "POST",
      credentials: "include",
    });

    if (!res.ok) {
      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: "Could not cancel this action.",
        },
      ]);

      return;
    }

    const data = await res.json();

    setChatMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        text: data.message,
      },
    ]);

    if (selectedCase) await refreshSelectedCaseData(selectedCase.id);
  };

  const toggleSection = (section: string) => {
    setOpenSections((prev) => ({
      ...prev,
      [section]: !prev[section],
    }));
  };

  if (!user) {
    return (
      <main className="loginShell">
        <section className="loginCard">
          <div className="loginInner">
            <div className="brand loginBrand">
              <div className="brandMark">D</div>
              <div className="brandText">
                <strong>DocketIQ</strong>
                <span>AI legal operations demo</span>
              </div>
            </div>

            <h1>Agentic Legal Operations Platform</h1>

            <p>
              Sign in with Google to access case operations, document intelligence,
              Gmail actions, Calendar scheduling, and attorney-ready handoff reports.
            </p>

            <button className="darkButton" onClick={login}>
              Continue with Google
            </button>
          </div>
        </section>
      </main>
    );
  }

  const renderDashboard = () => (
    <div className="viewStack">
      <div className="searchShell">
        <div>
          <strong>Search Dashboard</strong>
          <span>
            Search by client, case number, priority, status, insurer, claim, or summary.
          </span>
        </div>

        <input
          value={dashboardSearch}
          onChange={(event) => setDashboardSearch(event.target.value)}
          placeholder="Search dashboard cases..."
        />

        {dashboardSearch && (
          <button onClick={() => setDashboardSearch("")}>Clear</button>
        )}
      </div>

      <section className="statsGrid">
        <button
          className={`statCard ${dashboardFilter === "all" ? "activeStat" : ""}`}
          data-tooltip="Show all cases assigned to you."
          onClick={() => setDashboardFilter("all")}
        >
          <span>Active Cases</span>
          <strong>{dashboardData?.stats?.totalCases || 0}</strong>
        </button>

        <button
          className={`statCard ${dashboardFilter === "highPriority" ? "activeStat" : ""}`}
          data-tooltip="Filter dashboard to high-priority cases."
          onClick={() => setDashboardFilter("highPriority")}
        >
          <span>High Priority</span>
          <strong>{dashboardData?.stats?.highPriority || 0}</strong>
        </button>

        <button
          className={`statCard ${dashboardFilter === "openTasks" ? "activeStat" : ""}`}
          data-tooltip="Filter dashboard to cases with open tasks."
          onClick={() => setDashboardFilter("openTasks")}
        >
          <span>Open Tasks</span>
          <strong>{dashboardData?.stats?.openTasks || 0}</strong>
        </button>

        <button
          className={`statCard ${dashboardFilter === "pendingActions" ? "activeStat" : ""}`}
          data-tooltip="Filter dashboard to cases with pending emails or calendar actions."
          onClick={() => setDashboardFilter("pendingActions")}
        >
          <span>Pending Actions</span>
          <strong>{dashboardData?.stats?.pendingActions || 0}</strong>
        </button>

        <button
          className={`statCard ${dashboardFilter === "documents" ? "activeStat" : ""}`}
          data-tooltip="Filter dashboard to cases with uploaded documents."
          onClick={() => setDashboardFilter("documents")}
        >
          <span>Documents</span>
          <strong>{dashboardData?.stats?.documentCount || 0}</strong>
        </button>
      </section>

      <section className="dashboardTwoCol">
        <div className="panel scrollPanel">
          <h2>Case Portfolio</h2>
          <p className="mutedText">All cases available to your account.</p>

          <div className="caseCardGrid">
            {dashboardCases.map((caseItem) => (
              <button
                key={caseItem.id}
                className="casePortfolioCard hoverCard"
                data-tooltip="Open this case workspace."
                onClick={() => openCaseWorkspace(caseItem)}
              >
                <strong>{caseItem.case_number}</strong>
                <h3>{caseItem.client_name}</h3>
                <p>{caseItem.summary || "No summary available."}</p>
                <div className="pillRow">
                  <span>{caseItem.priority}</span>
                  <span>{caseItem.status}</span>
                  <span>{caseItem.document_count || 0} docs</span>
                </div>
              </button>
            ))}

            {!dashboardCases.length && (
              <div className="emptySearch">
                No dashboard cases match this search and filter.
              </div>
            )}
          </div>
        </div>

        <div className="panel scrollPanel">
          <h2>Operational Queue</h2>

          <div className="miniSection">
            <h3>Pending Actions</h3>
            {(dashboardData?.pendingActions || []).map((action) => (
              <div className="compactItem" key={action.id}>
                <strong>{action.action_type}</strong>
                <span>
                  {action.case_number} · {action.client_name}
                </span>
              </div>
            ))}

            {!dashboardData?.pendingActions?.length && (
              <p className="mutedText">No pending actions.</p>
            )}
          </div>

          <div className="miniSection">
            <h3>Live Calendar</h3>
            {calendarEvents.slice(0, 4).map((event) => (
              <div className="compactItem" key={event.id}>
                <strong>{event.title}</strong>
                <span>{formatDate(event.start_time)}</span>
              </div>
            ))}

            {!calendarEvents.length && (
              <p className="mutedText">No upcoming events.</p>
            )}
          </div>

          <div className="miniSection">
            <h3>Recent Activity</h3>
            {(dashboardData?.recentActivity || []).slice(0, 8).map((activity, index) => (
              <div className="compactItem" key={`${activity.action}-${index}`}>
                <strong>{activity.action}</strong>
                <span>{formatDate(activity.created_at)}</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );

  const renderCases = () => (
    <section className="panel scrollPanel tallPanel">
      <h2>Cases</h2>
      <p className="mutedText">Click a case to open the full workspace.</p>

      <div className="searchShell compactSearch">
        <div>
          <strong>Search Cases</strong>
          <span>Search by case number, client, status, priority, insurer, claim, or title.</span>
        </div>

        <input
          value={casesSearch}
          onChange={(event) => setCasesSearch(event.target.value)}
          placeholder="Search all cases..."
        />

        {casesSearch && (
          <button onClick={() => setCasesSearch("")}>Clear</button>
        )}
      </div>

      <div className="caseTable">
        {filteredCases.map((caseItem) => (
          <button
            key={caseItem.id}
            className="caseTableRow"
            onClick={() => openCaseWorkspace(caseItem)}
          >
            <div>
              <strong>{caseItem.case_number}</strong>
              <span>{caseItem.title}</span>
            </div>
            <div>{caseItem.client_name}</div>
            <div>{caseItem.priority}</div>
            <div>{caseItem.status}</div>
            <div>{caseItem.document_count || 0} docs</div>
          </button>
        ))}

        {!filteredCases.length && (
          <div className="emptySearch">No cases match your search.</div>
        )}
      </div>
    </section>
  );

  const renderNewCase = () => (
    <section className="panel intakePanel">
      <div className="intakeHeader">
        <div>
          <h2>New Case Intake</h2>
          <p className="mutedText">
            Create a new case through the Intake Agent. The system will generate
            the case, timeline, missing-item tasks, and first operational summary.
          </p>
        </div>
      </div>

      <div className="intakeGrid">
        <label>
          Client Name
          <input
            value={intakeForm.clientName}
            onChange={(event) => updateIntakeField("clientName", event.target.value)}
            placeholder="Alex Morgan"
          />
        </label>

        <label>
          Client Email
          <input
            value={intakeForm.clientEmail}
            onChange={(event) => updateIntakeField("clientEmail", event.target.value)}
            placeholder="alex@example.com"
          />
        </label>

        <label>
          Client Phone
          <input
            value={intakeForm.clientPhone}
            onChange={(event) => updateIntakeField("clientPhone", event.target.value)}
            placeholder="(801) 555-0101"
          />
        </label>

        <label>
          Preferred Language
          <input
            value={intakeForm.preferredLanguage}
            onChange={(event) =>
              updateIntakeField("preferredLanguage", event.target.value)
            }
            placeholder="English"
          />
        </label>

        <label>
          Case Type
          <input
            value={intakeForm.caseType}
            onChange={(event) => updateIntakeField("caseType", event.target.value)}
            placeholder="Personal Injury"
          />
        </label>

        <label>
          Incident Date
          <input
            type="date"
            value={intakeForm.incidentDate}
            onChange={(event) => updateIntakeField("incidentDate", event.target.value)}
          />
        </label>

        <label>
          Incident Type
          <input
            value={intakeForm.incidentType}
            onChange={(event) => updateIntakeField("incidentType", event.target.value)}
            placeholder="Rear-end collision"
          />
        </label>

        <label>
          Incident Location
          <input
            value={intakeForm.incidentLocation}
            onChange={(event) =>
              updateIntakeField("incidentLocation", event.target.value)
            }
            placeholder="Salt Lake City, UT"
          />
        </label>

        <label>
          Insurance Company
          <input
            value={intakeForm.insuranceCompany}
            onChange={(event) =>
              updateIntakeField("insuranceCompany", event.target.value)
            }
            placeholder="Mountain West Mutual"
          />
        </label>

        <label>
          Claim Number
          <input
            value={intakeForm.claimNumber}
            onChange={(event) => updateIntakeField("claimNumber", event.target.value)}
            placeholder="UT-123456"
          />
        </label>

        <label>
          Priority
          <select
            value={intakeForm.priority}
            onChange={(event) => updateIntakeField("priority", event.target.value)}
          >
            <option>Low</option>
            <option>Medium</option>
            <option>High</option>
          </select>
        </label>

        <label className="wideField">
          Intake Notes
          <textarea
            value={intakeForm.intakeNotes}
            onChange={(event) => updateIntakeField("intakeNotes", event.target.value)}
            placeholder="Client was involved in a rear-end collision. Police report not yet available. Treatment records pending. Insurance claim opened..."
          />
        </label>
      </div>

      <div className="intakeActions">
        <button
          className="primaryButton"
          onClick={createIntakeCase}
          disabled={isCreatingCase}
        >
          {isCreatingCase ? "Creating Case..." : "Create Case with Intake Agent"}
        </button>
      </div>
    </section>
  );

  const renderCaseWorkspace = () => {
    if (!selectedCase) {
      return (
        <section className="panel">
          <h2>No case selected</h2>
          <p className="mutedText">
            Go to Cases and select a case to open the workspace.
          </p>
        </section>
      );
    }

    return (
      <section className="workspaceGrid">
        <div className="workspaceMain">
          <section className="caseHero">
            <p>{selectedCase.case_number}</p>
            <h2>{selectedCase.title}</h2>
            <p>{selectedCase.summary || "No summary available."}</p>

            <div className="caseMetaGrid">
              <div className="caseMetaBox">
                <span>Client</span>
                <strong>{selectedCase.client_name}</strong>
              </div>
              <div className="caseMetaBox">
                <span>Claim</span>
                <strong>{selectedCase.claim_number || "Not added"}</strong>
              </div>
              <div className="caseMetaBox">
                <span>Insurance</span>
                <strong>{selectedCase.insurance_company || "Not added"}</strong>
              </div>
            </div>

            <div className="actionRow">
              <button className="primaryButton" onClick={() => refreshAutopilot(false)}>
                Refresh Autopilot
              </button>
              <button className="lightButton" onClick={openChat}>
                Open Chat
              </button>
            </div>
          </section>

          <section className="accordionPanel">
            <button
              className="accordionHeader"
              onClick={() => toggleSection("missingItems")}
            >
              <div>
                <strong>Missing Items & Open Tasks</strong>
                <span>{missingItemTasks.length} priority items</span>
              </div>
              <span>{openSections.missingItems ? "−" : "+"}</span>
            </button>

            {openSections.missingItems && (
              <div className="accordionBody">
                <div className="sectionToolbar">
                  <button
                    className="darkButton"
                    onClick={runMissingItems}
                    disabled={isRunningAgent}
                  >
                    Run Missing Items Agent
                  </button>

                  <label className="inlineUpload">
                    Upload Missing Document
                    <input
                      type="file"
                      accept="application/pdf"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) uploadDocument(file);
                      }}
                    />
                  </label>
                </div>

                <div className="scrollList">
                  {missingItemTasks.map((task) => (
                    <div
                      className="expandCard"
                      key={task.id}
                      onClick={() =>
                        setExpandedTask(expandedTask === task.id ? null : task.id)
                      }
                    >
                      <div className="expandTop">
                        <strong>{task.title}</strong>
                        <span>
                          {task.priority} · {task.status}
                        </span>
                      </div>

                      {expandedTask === task.id && (
                        <p>{task.description || "No description available."}</p>
                      )}
                    </div>
                  ))}

                  {!missingItemTasks.length && (
                    <p className="mutedText">
                      No missing items yet. Run the Missing Items Agent.
                    </p>
                  )}
                </div>
              </div>
            )}
          </section>

          <section className="accordionPanel">
            <button
              className="accordionHeader"
              onClick={() => toggleSection("documents")}
            >
              <div>
                <strong>Documents</strong>
                <span>{documents.length} uploaded files</span>
              </div>
              <span>{openSections.documents ? "−" : "+"}</span>
            </button>

            {openSections.documents && (
              <div className="accordionBody">
                <label className="uploadBox">
                  {isUploading ? "Processing PDF..." : "Upload Case PDF"}
                  <input
                    type="file"
                    accept="application/pdf"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) uploadDocument(file);
                    }}
                  />
                </label>

                <div className="scrollList">
                  {documents.map((doc) => (
                    <div className="compactItem" key={doc.id}>
                      <strong>{doc.file_name}</strong>
                      <span>
                        {doc.status} · {doc.text_char_count} chars ·{" "}
                        {formatDate(doc.created_at)}
                      </span>
                    </div>
                  ))}

                  {!documents.length && (
                    <p className="mutedText">No documents uploaded yet.</p>
                  )}
                </div>
              </div>
            )}
          </section>

          <section className="accordionPanel">
            <button
              className="accordionHeader"
              onClick={() => toggleSection("timeline")}
            >
              <div>
                <strong>Case Timeline</strong>
                <span>{timelineEvents.length} events</span>
              </div>
              <span>{openSections.timeline ? "−" : "+"}</span>
            </button>

            {openSections.timeline && (
              <div className="accordionBody timelineScroll">
                <div className="sectionToolbar">
                  <button
                    className="darkButton"
                    onClick={runTimeline}
                    disabled={isRunningAgent}
                  >
                    Run Timeline Agent
                  </button>
                </div>

                <div className="timeline">
                  {timelineEvents.map((event) => (
                    <div className="timelineItem" key={event.id}>
                      <div className="timelineDot" />
                      <div
                        className="timelineCard"
                        onClick={() =>
                          setExpandedTimelineItem(
                            expandedTimelineItem === event.id ? null : event.id
                          )
                        }
                      >
                        <strong>{event.title}</strong>
                        <span>
                          {formatShortDate(event.event_date)} · {event.event_type}
                        </span>

                        {expandedTimelineItem === event.id && (
                          <div className="timelineDetails">
                            <p>{event.description || "No details available."}</p>
                            <small>Source: {event.source || "DocketIQ"}</small>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}

                  {!timelineEvents.length && (
                    <p className="mutedText">
                      No timeline events yet. Run the Timeline Agent.
                    </p>
                  )}
                </div>
              </div>
            )}
          </section>

          <section className="accordionPanel">
            <button
              className="accordionHeader"
              onClick={() => toggleSection("agents")}
            >
              <div>
                <strong>Professional Agent Reports</strong>
                <span>Readiness, contradictions, next actions, relationships</span>
              </div>
              <span>{openSections.agents ? "−" : "+"}</span>
            </button>

            {openSections.agents && (
              <div className="accordionBody">
                <div className="agentGrid">
                  <button onClick={runReadiness} disabled={isRunningAgent}>
                    Readiness
                  </button>
                  <button onClick={runContradictions} disabled={isRunningAgent}>
                    Contradictions
                  </button>
                  <button onClick={runNextBestAction} disabled={isRunningAgent}>
                    Next Best Action
                  </button>
                  <button onClick={runRelationshipAgent} disabled={isRunningAgent}>
                    Relationships
                  </button>
                  <button onClick={downloadHandoffReport} disabled={isRunningAgent}>
                    Download Handoff
                  </button>
                </div>

                {isRunningAgent && <p className="mutedText">Running agent...</p>}

                {agentResult && (
                  <div className="reportCard">
                    <strong>{agentResult.title}</strong>
                    <p>{agentResult.subtitle}</p>
                    <pre>{stringifyReport(agentResult.payload)}</pre>
                  </div>
                )}
              </div>
            )}
          </section>
        </div>

        <aside className="workspaceSide">
          <section className="accordionPanel">
            <button
              className="accordionHeader"
              onClick={() => toggleSection("autopilot")}
            >
              <div>
                <strong>Communication Autopilot</strong>
                <span>{suggestions.length} suggestions</span>
              </div>
              <span>{openSections.autopilot ? "−" : "+"}</span>
            </button>

            {openSections.autopilot && (
              <div className="accordionBody sideScroll">
                <button
                  className="primaryButton fullButton"
                  onClick={() => refreshAutopilot(false)}
                >
                  Refresh Suggestions
                </button>

                <div className="autopilotStatus">
                  <span>Auto-runs every 30 minutes for the selected case.</span>
                  <span>
                    {isAutopilotSyncing
                      ? "Syncing..."
                      : lastAutopilotAt
                        ? `Last run ${formatDate(lastAutopilotAt)}`
                        : "Waiting for next auto-run"}
                  </span>
                </div>

                {suggestions.map((suggestion) => {
                  const payload = suggestion.draft_payload || {};

                  return (
                    <div
                      className="expandCard"
                      key={suggestion.id}
                      onClick={() =>
                        setExpandedSuggestion(
                          expandedSuggestion === suggestion.id ? null : suggestion.id
                        )
                      }
                    >
                      <div className="expandTop">
                        <strong>{suggestion.title}</strong>
                        <span>{suggestion.priority}</span>
                      </div>

                      {expandedSuggestion === suggestion.id && (
                        <div>
                          <p>{suggestion.reason}</p>
                          <p>
                            <strong>To:</strong> {payload.toEmail || "Not available"}
                          </p>
                          <p>
                            <strong>Subject:</strong>{" "}
                            {payload.subject || "Not available"}
                          </p>
                          <button
                            className="primaryButton"
                            onClick={(event) => {
                              event.stopPropagation();
                              convertSuggestionToAction(suggestion.id);
                            }}
                          >
                            Convert to Pending Email
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}

                {!suggestions.length && (
                  <p className="mutedText">No suggestions yet.</p>
                )}
              </div>
            )}
          </section>

          <section className="accordionPanel">
            <button className="accordionHeader" onClick={() => toggleSection("graph")}>
              <div>
                <strong>Case Context Graph</strong>
                <span>{graphData.nodes.length} nodes</span>
              </div>
              <span>{openSections.graph ? "−" : "+"}</span>
            </button>

            {openSections.graph && (
              <div className="accordionBody sideScroll">
                {graphData.nodes.map((node) => (
                  <div className={`graphNode ${node.type}`} key={node.id}>
                    <strong>{node.label}</strong>
                    <span>{node.subtitle}</span>
                  </div>
                ))}

                {!graphData.nodes.length && (
                  <p className="mutedText">No graph data yet.</p>
                )}
              </div>
            )}
          </section>

          <section className="accordionPanel">
            <button className="accordionHeader" onClick={() => toggleSection("reports")}>
              <div>
                <strong>Report History</strong>
                <span>{agentRuns.length} agent runs</span>
              </div>
              <span>{openSections.reports ? "−" : "+"}</span>
            </button>

            {openSections.reports && (
              <div className="accordionBody sideScroll">
                {agentRuns.map((run) => (
                  <div className="compactItem" key={run.id}>
                    <strong>{run.agent_name}</strong>
                    <span>{formatDate(run.created_at)}</span>
                  </div>
                ))}

                {!agentRuns.length && (
                  <p className="mutedText">No reports yet.</p>
                )}
              </div>
            )}
          </section>
        </aside>
      </section>
    );
  };

  const renderCalendar = () => (
    <section className="panel scrollPanel tallPanel">
      <h2>Calendar</h2>

      <div className="searchShell compactSearch">
        <div>
          <strong>Search Calendar</strong>
          <span>Search live calendar events by title, description, date, or source.</span>
        </div>

        <input
          value={calendarSearch}
          onChange={(event) => setCalendarSearch(event.target.value)}
          placeholder="Search calendar events..."
        />

        {calendarSearch && (
          <button onClick={() => setCalendarSearch("")}>Clear</button>
        )}
      </div>

      <div className="calendarHeaderRow">
        <p className="mutedText">
          Live Google Calendar events from the signed-in account. This refreshes
          silently every 10 seconds.
        </p>

        <span className="syncPill">
          {calendarSyncedAt ? `Synced ${formatDate(calendarSyncedAt)}` : "Syncing..."}
        </span>
      </div>

      <div className="calendarGrid">
        {filteredCalendarEvents.map((event) => (
          <div className="calendarEventCard" key={event.id}>
            <strong>{event.title}</strong>
            <span>
              {formatDate(event.start_time)} → {formatDate(event.end_time)}
            </span>
            {event.google_event_link && (
              <a href={event.google_event_link} target="_blank" rel="noreferrer">
                Open in Google Calendar
              </a>
            )}
          </div>
        ))}

        {!filteredCalendarEvents.length && (
          <p className="mutedText">No calendar events match your search.</p>
        )}
      </div>
    </section>
  );

  const renderReports = () => (
    <div className="viewStack">
      <div className="searchShell">
        <div>
          <strong>Search Reports</strong>
          <span>
            Search agent runs and handoff reports by case, client, agent, type, or summary.
          </span>
        </div>

        <input
          value={reportsSearch}
          onChange={(event) => setReportsSearch(event.target.value)}
          placeholder="Search reports and agent runs..."
        />

        {reportsSearch && (
          <button onClick={() => setReportsSearch("")}>Clear</button>
        )}
      </div>

      <section className="dashboardTwoCol">
        <div className="panel scrollPanel tallPanel">
          <h2>Agent Runs</h2>
          <p className="mutedText">
            Professional agent outputs generated across all accessible cases.
          </p>

          {filteredAgentRuns.map((run) => (
            <div className="compactItem" key={run.id}>
              <strong>{run.agent_name}</strong>
              <span>
                {run.case_number} · {run.client_name} · {formatDate(run.created_at)}
              </span>
              {run.result_summary && (
                <p className="mutedText">{run.result_summary}</p>
              )}
            </div>
          ))}

          {!filteredAgentRuns.length && (
            <p className="mutedText">No agent runs match this search.</p>
          )}
        </div>

        <div className="panel scrollPanel tallPanel">
          <h2>PDF / Handoff Reports</h2>
          <p className="mutedText">
            Attorney handoff reports and generated report records.
          </p>

          {filteredReports.map((report) => (
            <div className="compactItem" key={report.id}>
              <strong>{report.title}</strong>
              <span>
                {report.case_number} · {report.client_name} · {report.report_type} ·{" "}
                {formatDate(report.created_at)}
              </span>
            </div>
          ))}

          {!filteredReports.length && (
            <p className="mutedText">No report records match this search.</p>
          )}
        </div>
      </section>
    </div>
  );

  const renderActiveView = () => {
    if (activeView === "Dashboard") return renderDashboard();
    if (activeView === "Cases") return renderCases();
    if (activeView === "New Case") return renderNewCase();
    if (activeView === "Case Workspace") return renderCaseWorkspace();
    if (activeView === "Calendar") return renderCalendar();
    if (activeView === "Reports") return renderReports();

    return renderDashboard();
  };

  return (
    <>
      <div className="appLayout">
        <aside className="sidebar">
          <div className="brand">
            <div className="brandMark">D</div>
            <div className="brandText">
              <strong>DocketIQ</strong>
              <span>Legal Ops AI</span>
            </div>
          </div>

          <nav className="nav">
            {navItems.map((item) => (
              <button
                key={item}
                className={activeView === item ? "active" : ""}
                onClick={() => setActiveView(item)}
                data-tooltip={`Open ${item}`}
              >
                {item}
              </button>
            ))}
          </nav>
        </aside>

        <main className="main">
          <header className="topBar">
            <div className="pageTitle">
              <h1>{activeView}</h1>
              <p>
                {activeView === "Case Workspace" && selectedCase
                  ? `${selectedCase.case_number} · ${selectedCase.client_name}`
                  : "Agentic legal operations dashboard with case intelligence, communications, calendar, and reports."}
              </p>
            </div>

            <div className="profilePill">
              {user.avatarUrl && <img src={user.avatarUrl} alt={user.fullName} />}
              <div>
                <strong>{user.fullName}</strong>
                <span>{user.role}</span>
              </div>
              <button className="logoutButton" onClick={logout}>
                Logout
              </button>
            </div>
          </header>

          {renderActiveView()}
        </main>
      </div>

      {isChatMounted && (
        <section className={`chatPanel ${isChatClosing ? "closing" : "open"}`}>
          <div className="chatHeader">
            <strong>DocketIQ Assistant</strong>
            <span>{activeCaseSummary}</span>
          </div>

          <div className="chatMessages">
            {!selectedCase && (
              <div className="chatMessage assistant">
                No case selected. I can still answer dashboard-level questions like case
                counts, high-priority cases, open tasks, pending actions, reports, and
                recent activity. Open a case when you want case-specific actions.
              </div>
            )}

            {chatMessages.map((message, index) => (
              <div className={`chatMessage ${message.role}`} key={index}>
                <div>{message.text}</div>

                {message.pendingAction && (
                  <div className="actionButtons">
                    <button onClick={() => confirmAction(message.pendingAction!.id)}>
                      Confirm
                    </button>
                    <button onClick={() => cancelAction(message.pendingAction!.id)}>
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            ))}

            {isThinking && <div className="chatMessage assistant">Thinking...</div>}
          </div>

          <div className="chatInput">
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder={
                selectedCase
                  ? `Ask about ${selectedCase.case_number}...`
                  : "Ask about dashboard, cases, priorities..."
              }
              onKeyDown={(event) => {
                if (event.key === "Enter") askQuestion();
              }}
            />
            <button className="darkButton" onClick={askQuestion}>
              Send
            </button>
          </div>
        </section>
      )}

      <div className="chatFab">
        <button className="chatBubbleButton" onClick={toggleChat}>
          {isChatMounted && !isChatClosing ? "×" : "AI"}
        </button>
      </div>
    </>
  );
}

export default App;