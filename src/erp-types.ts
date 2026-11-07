import type { Trace } from "./types";

export type View =
  | "overview"
  | "orders"
  | "customers"
  | "returns"
  | "conversations"
  | "support"
  | "activity"
  | "settings";
export interface Customer {
  customer_id: string;
  display_id?: string;
  first_name: string;
  last_name?: string;
  email: string;
  phone: string;
  city?: string;
  notes?: string;
  created_at?: string;
}
export interface Product {
  sku: string;
  name: string;
  price: number;
  color: string;
  image?: string;
}
export interface Item {
  item_id: string;
  name: string;
  sku?: string;
  size?: string;
  color?: string;
  quantity: number;
  unit_price?: number;
  status: string;
  delivered_at: string | null;
  final_sale: boolean;
  returned: boolean;
  image?: string;
}
export interface Order {
  order_id: string;
  customer_id: string;
  status: string;
  carrier: string;
  carrier_eta_date: string | null;
  tracking_reference?: string;
  ordered_at?: string;
  source_updated_at: string;
  shipping_city?: string;
  order_total: number;
  currency: string;
  payment_status?: string;
  priority?: string;
  notes?: string;
  revision?: number;
  policy_version: string;
  items: Item[];
}
export interface ReturnRecord {
  id: string;
  order_id: string;
  customer_id: string;
  item_id: string;
  item_name: string;
  quantity: number;
  reason: string;
  status: string;
  notes: string;
  refund_amount: number;
  created_at: string;
  updated_at: string;
  source?: string;
  condition?: string;
  tags?: string;
  photos?: { url: string; id: string }[];
  pickup_address?: string;
  pickup_preference?: string;
  pickup_date?: string;
  pickup_reference?: string;
  inspection?: string;
  refund_reference?: string;
  review_required?: boolean;
  public_reason?: string;
}
export interface Ticket {
  id: string;
  customer: string;
  order_id: string | null;
  reason: string;
  request: string;
  status: string;
  assignee?: string;
  internal_note?: string;
  created_at: string;
  queue_message: string;
  source_failure?: string | null;
  transcript: { role: string; content: string }[];
}
export interface Conversation {
  reference: string;
  customer_id: string | null;
  customer_name: string;
  stage: string;
  order_id: string | null;
  last_message: string;
  updated_at: string;
  message_count: number;
  verification_code: string | null;
  mode: string | null;
}
export interface ConversationDetail {
  reference: string;
  stage: string;
  verification_code: string | null;
  latest_trace: Trace | null;
  messages: {
    id: string;
    role: string;
    text: string;
    at: string;
    media?: { url: string };
    product?: { image?: string; name: string; amount: number; variant: string };
  }[];
}
export interface Activity {
  id: string;
  at: string;
  entity: string;
  entity_id: string;
  action: string;
  summary: string;
  changes: Record<string, unknown>;
  actor: string;
}
export interface Settings {
  demo_now: string;
  verification_mode: "demo_match" | "code";
  inference_mode: "model" | "baseline";
  order_api_available: boolean;
  feed_health: string;
  ticket_store_available: boolean;
  business_timezone: string;
}
export interface Workspace {
  orders: Order[];
  customers: Customer[];
  returns: ReturnRecord[];
  tickets: Ticket[];
  conversations: Conversation[];
  activity: Activity[];
  catalog: Product[];
  settings: Settings;
}
export type Detail = {
  kind: "order" | "customer" | "return" | "ticket" | "conversation";
  id: string;
} | null;
export type Api = <T>(
  path: string,
  method?: string,
  body?: unknown,
) => Promise<T>;
export const titles: Record<View, string> = {
  overview: "Overview",
  orders: "Orders",
  customers: "Customers",
  returns: "Returns",
  conversations: "Conversations",
  support: "Support queue",
  activity: "Activity log",
  settings: "Settings",
};
export const labels: Record<string, string> = {
  processing: "Unfulfilled",
  in_transit: "In transit",
  delivered: "Delivered",
  partially_delivered: "Partially delivered",
  cancelled: "Cancelled",
  returned: "Returned",
  paid: "Paid",
  pending: "Payment pending",
  partially_refunded: "Partially refunded",
  refunded: "Refunded",
  requested: "Requested",
  approved: "Approved",
  pickup_scheduled: "Pickup scheduled",
  declined: "Declined",
  received: "Received",
  queued: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
  contact: "Needs identification",
  code: "Awaiting code",
  choose_order: "Choosing order",
  verified: "Account matched",
  model: "Qwen3-8B",
  baseline: "Rules",
  system: "System update",
  baseline_fallback: "Fallback",
};
export const name = (customer?: Customer) =>
  customer
    ? `${customer.first_name} ${customer.last_name || ""}`.trim()
    : "Unknown customer";
export const money = (value = 0) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(
    value,
  );
export const day = (value?: string | null) =>
  value
    ? new Date(
        value.length === 10 ? value + "T12:00:00Z" : value,
      ).toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : "—";
export const stamp = (value?: string) =>
  value
    ? new Date(value).toLocaleString("en-GB", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
