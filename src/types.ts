export interface Item { item_id: string; name: string; status: string; delivered_at: string | null; final_sale: boolean; returned: boolean }
export interface Order { order_id: string; customer_id: string; status: string; carrier: string; carrier_eta_date: string | null; source_updated_at: string; fetched_at?: string; policy_version: string; items: Item[] }
export interface Action { label: string; text: string }
export interface Trace { id: string; mode: string; model: string | null; latency_ms: number; outcome: string; note: string | null; at: string; steps: { name: string; state: string; detail: string }[]; usage: { input_tokens: number; output_tokens: number }; proposal?: { name: string; arguments: Record<string, string> }; evidence?: Order }
export interface Ticket { id: string; order_id: string | null; reason: string; status: string; created_at: string; request: string; verification: string; customer: string | null; evidence: Order | null; source_failure: string | null; queue_message: string; transcript: { role: string; content: string }[] }
export interface ReturnCard { type: 'return'; order_id: string; item_name: string; decision: string; reason: string; policy_version: string; deadline: string | null }
export interface Reply { message: string; outcome: string; card: ({ type: 'order' } & Order) | ({ type: 'ticket' } & Ticket) | ReturnCard | null; actions: Action[]; trace: Trace }
export interface Message { id: string; role: 'user' | 'assistant'; text: string; reply?: Reply }
export interface Settings { order_api_available: boolean; feed_health: string; ticket_store_available: boolean; demo_now: string; business_timezone: string }
export interface Studio { orders: Order[]; tickets: Ticket[]; traces: Trace[]; settings: Settings }
export interface ModelHealth { ready: boolean; model: string; provider: string; region: string }
