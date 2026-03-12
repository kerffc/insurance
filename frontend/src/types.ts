export interface Client {
  id: string;
  name: string;
  email: string;
  phone: string;
  whatsapp: string;
  insurer: string;
  policy_type: string;
  policy_number: string;
  plan_name: string;
  remarks: string;
}

export interface PolicyChange {
  id: string;
  insurer: string;
  product_line: string;
  plan_names: string[];
  change_title: string;
  change_description: string;
  effective_date: string;
  impact_summary: string;
  source_url?: string;
  created_at: string;
  created_by: string;
}

export interface Notification {
  id: string;
  client_id: string;
  client_name: string;
  channel: string;
  message: string;
  error?: string;
  status: "pending" | "reviewed" | "sent";
  reviewed_at?: string;
  sent_at?: string;
  edited: boolean;
}

export interface Session {
  id: string;
  created_at: string;
  created_by: string;
  policy_change_id: string;
  policy_change_title?: string;
  clients: Client[];
  notifications: Notification[];
}

export interface SessionSummary {
  id: string;
  created_at: string;
  created_by: string;
  policy_change_id: string;
  total_clients: number;
  total_notifications: number;
  sent_count: number;
}

export type View = "upload" | "policy-change" | "review" | "dashboard";
