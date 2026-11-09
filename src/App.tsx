import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity as ActivityIcon,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Check,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  ExternalLink,
  Inbox,
  LayoutDashboard,
  LoaderCircle,
  Menu,
  MessageSquare,
  MoreHorizontal,
  Package,
  Plus,
  RefreshCw,
  Search,
  Settings as SettingsIcon,
  ShoppingBag,
  Users,
  X,
} from "lucide-react";
import { useWorkspace } from "./useWorkspace";
import {
  ActivityList,
  Badge,
  ConversationView,
  DeliveryEstimateForm,
  CustomerDetails,
  CustomerForm,
  Empty,
  Modal,
  NewOrderForm,
  NewReturnForm,
  OrderDetails,
  ReturnDetails,
  SupportDetails,
} from "./OperationsForms";
import type {
  ConversationDetail,
  Customer,
  Detail,
  Order,
  ReturnRecord,
  View,
  Workspace,
} from "./erp-types";
import { day, labels, money, name, stamp, titles } from "./erp-types";

const NAV: { id: View; icon: typeof Package }[] = [
  { id: "overview", icon: LayoutDashboard },
  { id: "orders", icon: ShoppingBag },
  { id: "customers", icon: Users },
  { id: "returns", icon: RefreshCw },
  { id: "conversations", icon: MessageSquare },
  { id: "support", icon: Inbox },
  { id: "activity", icon: ActivityIcon },
];
type ModalState =
  | { kind: "customer"; customerId?: string }
  | { kind: "order"; customerId?: string; initialSize?: string }
  | { kind: "return"; orderId?: string }
  | { kind: "estimate"; orderId: string }
  | { kind: "demo" }
  | null;
function initialView(): View {
  const hash = location.hash.slice(1) as View;
  return hash in titles ? hash : "orders";
}
function customerFor(data: Workspace, id: string) {
  return data.customers.find((c) => c.customer_id === id);
}
function exportOrders(rows: Order[], data: Workspace) {
  const cell = (value: unknown) => {
    let text = String(value ?? "");
    if (/^[=+@-]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  const csv = [
    [
      "Order",
      "Customer",
      "Email",
      "Status",
      "Payment",
      "Total INR",
      "Delivery city",
      "Created",
    ],
    ...rows.map((o) => [
      o.order_id,
      name(customerFor(data, o.customer_id)),
      customerFor(data, o.customer_id)?.email,
      labels[o.status],
      o.payment_status || "paid",
      o.order_total,
      o.shipping_city,
      o.ordered_at,
    ]),
  ]
    .map((row) => row.map(cell).join(","))
    .join("\r\n");
  const url = URL.createObjectURL(
    new Blob([csv], { type: "text/csv;charset=utf-8;" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "threadline-orders.csv";
  link.click();
  URL.revokeObjectURL(url);
}

export default function App() {
  const { data, api, reload, connected, loading, error, setError } =
    useWorkspace();
  const [view, setView] = useState<View>(initialView),
    [search, setSearch] = useState(""),
    [filter, setFilter] = useState("all"),
    [detail, setDetail] = useState<Detail>(null),
    [modal, setModal] = useState<ModalState>(null);
  const [toast, setToast] = useState(""),
    [mobileNav, setMobileNav] = useState(false),
    [busy, setBusy] = useState(false),
    [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const notify = useCallback((text: string) => setToast(text), []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 4000);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    document.title = `${titles[view]} · Threadline`;
    history.replaceState(null, "", "#" + view);
  }, [view]);
  useEffect(() => {
    const onHash = () => {
      setView(initialView());
      setSearch("");
      setFilter("all");
      setDetail(null);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    if (!detail) return;
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !modal) setDetail(null);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [detail, modal]);
  const activeConversation =
    detail?.kind === "conversation"
      ? data?.conversations.find((c) => c.reference === detail.id)
      : null;
  useEffect(() => {
    if (detail?.kind !== "conversation") {
      setConversation(null);
      return;
    }
    let live = true;
    api<ConversationDetail>("/conversations/" + detail.id)
      .then((r) => {
        if (live) setConversation(r);
      })
      .catch((e) => setError(e.message));
    return () => {
      live = false;
    };
  }, [detail?.id, activeConversation?.updated_at, api, setError]);
  function navigate(next: View) {
    setView(next);
    setSearch("");
    setFilter("all");
    setDetail(null);
    setMobileNav(false);
  }
  async function mutate<T>(
    path: string,
    method: string,
    body?: unknown,
  ): Promise<T> {
    const result = await api<T>(path, method, body);
    await reload();
    return result;
  }
  async function setting(key: string, value: unknown) {
    try {
      await mutate("/controls", "PATCH", { [key]: value });
      notify("Settings saved");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const [savingOrder, setSavingOrder] = useState<string | null>(null);
  async function quickFulfil(order: Order, status: string) {
    if (status === order.status) return;
    setSavingOrder(order.order_id);
    try {
      await mutate(`/orders/${order.order_id}`, "PATCH", {
        status,
        revision: order.revision || 1,
      });
      notify(`Order #${order.order_id} · ${labels[status]} saved`);
    } catch (e) {
      setError((e as Error).message);
      await reload();
    } finally {
      setSavingOrder(null);
    }
  }
  async function restore() {
    setBusy(true);
    try {
      await mutate("/reset", "POST");
      setDetail(null);
      setModal(null);
      notify("Sample data restored");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const orders = useMemo(() => {
    if (!data) return [];
    const query = search.toLowerCase();
    return data.orders
      .filter((o) => {
        const c = customerFor(data, o.customer_id);
        const matches = [
          o.order_id,
          name(c),
          c?.email || "",
          o.tracking_reference || "",
          ...o.items.map((i) => i.name),
        ]
          .join(" ")
          .toLowerCase()
          .includes(query);
        const status =
          filter === "all" ||
          (filter === "processing"
            ? ["processing", "partially_delivered"].includes(o.status)
            : filter === "late"
              ? !!o.carrier_eta_date &&
                o.carrier_eta_date < data.settings.demo_now.slice(0, 10) &&
                o.status !== "delivered"
              : o.status === filter);
        return matches && status;
      })
      .sort((a, b) => (b.ordered_at || "").localeCompare(a.ordered_at || ""));
  }, [data, search, filter]);
  const customers =
    data?.customers
      .filter((c) =>
        [name(c), c.email, c.phone, c.customer_id, c.display_id]
          .join(" ")
          .toLowerCase()
          .includes(search.toLowerCase()),
      )
      .sort((a, b) => name(a).localeCompare(name(b))) || [];
  const returnRows =
    data?.returns.filter(
      (r) =>
        (filter === "all" || r.status === filter) &&
        [r.id, r.order_id, r.item_name, name(customerFor(data, r.customer_id))]
          .join(" ")
          .toLowerCase()
          .includes(search.toLowerCase()),
    ) || [];
  const tickets =
    data?.tickets.filter(
      (t) =>
        (filter === "all" || t.status === filter) &&
        [t.id, t.request, t.order_id, t.reason, t.assignee]
          .join(" ")
          .toLowerCase()
          .includes(search.toLowerCase()),
    ) || [];
  const conversations =
    data?.conversations.filter((c) =>
      [c.customer_name, c.reference, c.last_message, c.order_id]
        .join(" ")
        .toLowerCase()
        .includes(search.toLowerCase()),
    ) || [];
  const openOrders =
    data?.orders.filter((o) =>
      ["processing", "partially_delivered"].includes(o.status),
    ).length || 0;
  const returnCount =
    data?.returns.filter((r) => r.status === "requested").length || 0;
  const supportCount =
    data?.tickets.filter((t) => t.status !== "resolved").length || 0;
  const selectedOrder =
    detail?.kind === "order"
      ? data?.orders.find((o) => o.order_id === detail.id)
      : undefined;
  const selectedCustomer =
    detail?.kind === "customer"
      ? data?.customers.find((c) => c.customer_id === detail.id)
      : undefined;
  const selectedReturn =
    detail?.kind === "return"
      ? data?.returns.find((r) => r.id === detail.id)
      : undefined;
  const selectedTicket =
    detail?.kind === "ticket"
      ? data?.tickets.find((t) => t.id === detail.id)
      : undefined;
  const recordTitle =
    detail?.kind === "order"
      ? `Order #${detail.id}`
      : detail?.kind === "customer"
        ? name(selectedCustomer)
        : detail?.kind === "return"
          ? detail.id
          : detail?.kind === "ticket"
            ? detail.id
            : detail?.id || "";
  const pageDescription: Record<View, string> = {
    overview: "Current workload and recent store activity.",
    orders: "Manage fulfilment, delivery, and payment records.",
    customers: "Customer accounts and purchase history.",
    returns: "Review requests and track items through the return process.",
    conversations: "Customer messages from the WhatsApp channel.",
    support: "Requests that need a member of your team.",
    activity: "Changes recorded across the workspace.",
    settings: "Store configuration and demo environment controls.",
  };
  const orderTable = (rows: Order[], compact = false) => (
    <div className="erp-table-wrap">
      <table className={"erp-table " + (compact ? "compact" : "")}>
        <thead>
          <tr>
            <th>Order</th>
            {!compact && <th>Date</th>}
            <th>Customer</th>
            <th>Payment</th>
            <th>Fulfilment</th>
            {!compact && <th>Delivery estimate</th>}
            {!compact && <th>Items</th>}
            <th className="number">Total</th>
            <th className="erp-row-more">
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((o) => (
            <tr
              key={o.order_id}
              onClick={() => setDetail({ kind: "order", id: o.order_id })}
            >
              <td>
                <button
                  className="erp-row-link"
                  onClick={() => setDetail({ kind: "order", id: o.order_id })}
                >
                  #{o.order_id}
                </button>
                {o.priority === "high" && (
                  <span className="erp-row-priority" title="High priority">
                    !
                  </span>
                )}
              </td>
              {!compact && <td className="erp-muted">{day(o.ordered_at)}</td>}
              <td>
                <span className="erp-cell-primary">
                  {name(customerFor(data!, o.customer_id))}
                </span>
                {!compact && (
                  <span className="erp-cell-secondary">
                    {o.shipping_city || "—"}
                  </span>
                )}
              </td>
              <td>
                <Badge value={o.payment_status || "paid"} />
              </td>
              <td>
                <div
                  className={"erp-fulfil-select " + o.status}
                  onClick={(e) => e.stopPropagation()}
                >
                  <span className="erp-status-dot" />
                  <select
                    aria-label={`Fulfilment for order ${o.order_id}`}
                    value={o.status}
                    disabled={savingOrder === o.order_id}
                    onChange={(e) => void quickFulfil(o, e.target.value)}
                  >
                    {[
                      "processing",
                      "in_transit",
                      "partially_delivered",
                      "delivered",
                      "cancelled",
                      "returned",
                    ].map((s) => (
                      <option
                        value={s}
                        key={s}
                        disabled={s === "partially_delivered" && o.status !== s}
                      >
                        {labels[s]}
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={12} />
                </div>
                {o.carrier_eta_date &&
                  o.carrier_eta_date < data!.settings.demo_now.slice(0, 10) &&
                  o.status !== "delivered" && (
                    <span className="erp-late-note">
                      Past delivery estimate
                    </span>
                  )}
              </td>
              {!compact && (
                <td>
                  {["delivered", "returned", "cancelled"].includes(o.status) ? (
                    <span className="erp-muted">—</span>
                  ) : (
                    <button
                      className={
                        "erp-estimate-cell " +
                        (!o.carrier_eta_date ? "empty" : "")
                      }
                      aria-label={`Delivery estimate for order ${o.order_id}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setModal({ kind: "estimate", orderId: o.order_id });
                      }}
                    >
                      <CalendarDays size={14} />
                      <span>
                        {o.carrier_eta_date
                          ? day(o.carrier_eta_date)
                          : "Set estimate"}
                      </span>
                    </button>
                  )}
                </td>
              )}
              {!compact && (
                <td className="erp-muted">
                  {o.items.reduce((n, i) => n + i.quantity, 0)}{" "}
                  {o.items.reduce((n, i) => n + i.quantity, 0) === 1
                    ? "item"
                    : "items"}
                </td>
              )}
              <td className="number">{money(o.order_total)}</td>
              <td>
                <ChevronRight size={15} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && (
        <Empty
          title="No matching orders"
          text="Adjust the filters or create a new order."
        />
      )}
    </div>
  );
  return (
    <div className="erp-app">
      {mobileNav && (
        <div className="erp-nav-scrim" onClick={() => setMobileNav(false)} />
      )}
      <aside className={"erp-sidebar " + (mobileNav ? "open" : "")}>
        <a
          className="erp-brand"
          href="/#orders"
          onClick={(e) => {
            e.preventDefault();
            navigate("orders");
          }}
        >
          <span>
            <Package size={20} />
          </span>
          <div>
            Threadline<small>Retail operations</small>
          </div>
          <ChevronDown size={13} />
        </a>
        <div className="erp-workspace">
          <span className="erp-workspace-dot" />
          India store<span>INR</span>
        </div>
        <div className="erp-nav-label">WORKSPACE</div>
        <nav aria-label="Operations navigation">
          {NAV.map(({ id, icon: Icon }) => (
            <button
              key={id}
              className={view === id ? "active" : ""}
              onClick={() => navigate(id)}
            >
              <Icon size={17} />
              <span>{titles[id]}</span>
              {((id === "orders" && openOrders > 0) ||
                (id === "returns" && returnCount > 0) ||
                (id === "support" && supportCount > 0)) && (
                <small>
                  {id === "orders"
                    ? openOrders
                    : id === "returns"
                      ? returnCount
                      : supportCount}
                </small>
              )}
            </button>
          ))}
        </nav>
        <div className="erp-sidebar-bottom">
          <button
            onClick={() => navigate("settings")}
            className={view === "settings" ? "active" : ""}
          >
            <SettingsIcon size={17} />
            Settings
          </button>
          <button onClick={() => setModal({ kind: "demo" })}>
            <CircleHelp size={17} />
            Demo tools
          </button>
          <div className="erp-sidebar-user">
            <span>SA</span>
            <div>
              Store admin<small>Local workspace</small>
            </div>
            <MoreHorizontal size={16} />
          </div>
        </div>
      </aside>
      <div className="erp-main">
        <header className="erp-topbar">
          <div>
            <button
              className="erp-icon erp-menu"
              onClick={() => setMobileNav(!mobileNav)}
              aria-label="Toggle navigation"
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{titles[view]}</strong>
          </div>
          <div>
            <span className={"erp-live " + (connected ? "online" : "")}>
              <i />
              {connected ? "Live" : "Reconnecting"}
            </span>
            <a
              className="erp-button"
              href="/whatsapp"
              target="_blank"
              rel="noreferrer"
            >
              <MessageSquare size={15} />
              <span>Open customer chat</span>
              <ExternalLink size={12} />
            </a>
          </div>
        </header>
        <main className="erp-content">
          <div className="erp-page-heading">
            <div>
              <h1>{titles[view]}</h1>
              <p>{pageDescription[view]}</p>
            </div>
            <div className="erp-page-actions">
              {view === "orders" && data && (
                <button
                  className="erp-button"
                  onClick={() => {
                    exportOrders(orders, data);
                    notify("Order export downloaded");
                  }}
                >
                  <ArrowDownToLine size={15} />
                  Export
                </button>
              )}
              {["overview", "orders"].includes(view) && (
                <button
                  className="erp-button primary"
                  onClick={() => setModal({ kind: "order" })}
                >
                  <Plus size={16} />
                  Create order
                </button>
              )}
              {view === "customers" && (
                <button
                  className="erp-button primary"
                  onClick={() => setModal({ kind: "customer" })}
                >
                  <Plus size={16} />
                  Add customer
                </button>
              )}
              {view === "returns" && (
                <button
                  className="erp-button primary"
                  onClick={() => setModal({ kind: "return" })}
                >
                  <Plus size={16} />
                  Create return
                </button>
              )}
            </div>
          </div>
          {error && (
            <div className="erp-error" role="alert">
              <span>{error}</span>
              <button
                className="erp-icon"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={15} />
              </button>
            </div>
          )}
          {loading || !data ? (
            <div className="erp-loading">
              <LoaderCircle size={22} className="spin" />
              Loading workspace…
            </div>
          ) : (
            <>
              {view === "overview" && (
                <>
                  <div className="erp-metrics">
                    {[
                      {
                        label: "Total orders",
                        value: data.orders.length,
                        detail: `${data.orders.filter((o) => o.status === "delivered").length} delivered`,
                        view: "orders" as View,
                      },
                      {
                        label: "Awaiting fulfilment",
                        value: openOrders,
                        detail: "Unfulfilled or partially delivered",
                        view: "orders" as View,
                      },
                      {
                        label: "Return requests",
                        value: returnCount,
                        detail: `${data.returns.length} returns in total`,
                        view: "returns" as View,
                      },
                      {
                        label: "Open support",
                        value: supportCount,
                        detail: `${data.conversations.length} customer conversations`,
                        view: "support" as View,
                      },
                    ].map((m) => (
                      <button key={m.label} onClick={() => navigate(m.view)}>
                        <span>
                          {m.label}
                          <ArrowUpRight size={14} />
                        </span>
                        <strong>{m.value}</strong>
                        <small>{m.detail}</small>
                      </button>
                    ))}
                  </div>
                  <section className="erp-panel">
                    <header>
                      <h2>Orders in progress</h2>
                      <button
                        className="erp-text-button"
                        onClick={() => navigate("orders")}
                      >
                        View all orders
                        <ArrowRight size={14} />
                      </button>
                    </header>
                    {orderTable(
                      data.orders
                        .filter(
                          (o) =>
                            !["delivered", "cancelled", "returned"].includes(
                              o.status,
                            ),
                        )
                        .slice(0, 6),
                      true,
                    )}
                  </section>
                  <div className="erp-overview-grid">
                    <section className="erp-panel">
                      <header>
                        <h2>Recent activity</h2>
                        <button
                          className="erp-text-button"
                          onClick={() => navigate("activity")}
                        >
                          View log
                          <ArrowRight size={14} />
                        </button>
                      </header>
                      <div className="erp-panel-content">
                        <ActivityList rows={data.activity.slice(0, 5)} />
                      </div>
                    </section>
                    <section className="erp-panel">
                      <header>
                        <h2>Recent conversations</h2>
                        <button
                          className="erp-text-button"
                          onClick={() => navigate("conversations")}
                        >
                          View all
                          <ArrowRight size={14} />
                        </button>
                      </header>
                      {data.conversations.length ? (
                        <div className="erp-recent-conversations">
                          {data.conversations.slice(0, 5).map((c) => (
                            <button
                              key={c.reference}
                              onClick={() => {
                                setView("conversations");
                                setDetail({
                                  kind: "conversation",
                                  id: c.reference,
                                });
                              }}
                            >
                              <span className="erp-avatar">
                                {c.customer_name[0]}
                              </span>
                              <div>
                                <strong>{c.customer_name}</strong>
                                <p>{c.last_message.replaceAll("*", "")}</p>
                              </div>
                              <span>{stamp(c.updated_at)}</span>
                            </button>
                          ))}
                        </div>
                      ) : (
                        <Empty
                          title="No conversations yet"
                          text="Customer messages will appear here."
                        />
                      )}
                    </section>
                  </div>
                </>
              )}
              {view === "orders" && (
                <section className="erp-panel">
                  <div
                    className="erp-table-tabs"
                    role="group"
                    aria-label="Order filters"
                  >
                    {[
                      {
                        id: "all",
                        label: "All orders",
                        count: data.orders.length,
                      },
                      {
                        id: "processing",
                        label: "Unfulfilled",
                        count: openOrders,
                      },
                      {
                        id: "in_transit",
                        label: "In transit",
                        count: data.orders.filter(
                          (o) => o.status === "in_transit",
                        ).length,
                      },
                      {
                        id: "delivered",
                        label: "Delivered",
                        count: data.orders.filter(
                          (o) => o.status === "delivered",
                        ).length,
                      },
                      {
                        id: "cancelled",
                        label: "Cancelled",
                        count: data.orders.filter(
                          (o) => o.status === "cancelled",
                        ).length,
                      },
                    ].map((tab) => (
                      <button
                        key={tab.id}
                        className={filter === tab.id ? "active" : ""}
                        onClick={() => setFilter(tab.id)}
                      >
                        {tab.label}
                        <span>{tab.count}</span>
                      </button>
                    ))}
                  </div>
                  <div className="erp-list-toolbar">
                    <label className="erp-search">
                      <Search size={16} />
                      <input
                        aria-label="Search orders"
                        placeholder="Search order, customer, or tracking reference"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                      {search && (
                        <button
                          onClick={() => setSearch("")}
                          aria-label="Clear search"
                        >
                          <X size={13} />
                        </button>
                      )}
                    </label>
                    <span>{orders.length} orders</span>
                    <button
                      className="erp-icon"
                      onClick={() => reload()}
                      aria-label="Refresh orders"
                    >
                      <RefreshCw size={15} />
                    </button>
                  </div>
                  {orderTable(orders)}
                  <div className="erp-table-footer">
                    <span>
                      Showing {orders.length} of {data.orders.length} orders
                    </span>
                    <span>
                      <i className="erp-status-dot" />
                      Updates sync automatically
                    </span>
                  </div>
                </section>
              )}
              {view === "customers" && (
                <section className="erp-panel">
                  <div className="erp-list-toolbar">
                    <label className="erp-search">
                      <Search size={16} />
                      <input
                        aria-label="Search customers"
                        placeholder="Search name, email, phone, or customer ID"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </label>
                    <span>{customers.length} customers</span>
                  </div>
                  <div className="erp-table-wrap">
                    <table className="erp-table">
                      <thead>
                        <tr>
                          <th>Customer</th>
                          <th>Contact</th>
                          <th>Location</th>
                          <th>Orders</th>
                          <th className="number">Total spent</th>
                          <th>Added</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {customers.map((c) => {
                          const owned = data.orders.filter(
                            (o) => o.customer_id === c.customer_id,
                          );
                          return (
                            <tr
                              key={c.customer_id}
                              onClick={() =>
                                setDetail({
                                  kind: "customer",
                                  id: c.customer_id,
                                })
                              }
                            >
                              <td>
                                <div className="erp-person-cell">
                                  <span className="erp-avatar">
                                    {c.first_name[0]}
                                    {c.last_name?.[0] || ""}
                                  </span>
                                  <div>
                                    <button
                                      className="erp-row-link"
                                      onClick={() =>
                                        setDetail({
                                          kind: "customer",
                                          id: c.customer_id,
                                        })
                                      }
                                    >
                                      {name(c)}
                                    </button>
                                    <span className="erp-cell-secondary">
                                      {c.display_id || c.customer_id}
                                    </span>
                                  </div>
                                </div>
                              </td>
                              <td>
                                <span className="erp-cell-primary">
                                  {c.email}
                                </span>
                                <span className="erp-cell-secondary">
                                  {c.phone}
                                </span>
                              </td>
                              <td>{c.city || "—"}</td>
                              <td>{owned.length}</td>
                              <td className="number">
                                {money(
                                  owned
                                    .filter((o) => o.status !== "cancelled")
                                    .reduce((sum, o) => sum + o.order_total, 0),
                                )}
                              </td>
                              <td className="erp-muted">{day(c.created_at)}</td>
                              <td>
                                <ChevronRight size={15} />
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {!customers.length && (
                      <Empty
                        title="No customers found"
                        text="Add a customer or try a different search."
                      />
                    )}
                  </div>
                  <div className="erp-table-footer">
                    <span>{customers.length} customer accounts</span>
                    <span>Email and phone match the customer chat</span>
                  </div>
                </section>
              )}
              {view === "returns" && (
                <section className="erp-panel">
                  <div className="erp-table-tabs">
                    {[
                      "all",
                      "requested",
                      "approved",
                      "pickup_scheduled",
                      "received",
                      "refunded",
                      "declined",
                    ].map((s) => (
                      <button
                        key={s}
                        className={filter === s ? "active" : ""}
                        onClick={() => setFilter(s)}
                      >
                        {s === "all" ? "All returns" : labels[s]}
                        <span>
                          {s === "all"
                            ? data.returns.length
                            : data.returns.filter((r) => r.status === s).length}
                        </span>
                      </button>
                    ))}
                  </div>
                  <div className="erp-list-toolbar">
                    <label className="erp-search">
                      <Search size={16} />
                      <input
                        aria-label="Search returns"
                        placeholder="Search return, order, or customer"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </label>
                    <span>{returnRows.length} returns</span>
                  </div>
                  <div className="erp-table-wrap">
                    <table className="erp-table">
                      <thead>
                        <tr>
                          <th>Return</th>
                          <th>Order / customer</th>
                          <th>Item</th>
                          <th>Reason</th>
                          <th>Status</th>
                          <th className="number">Refund value</th>
                          <th>Requested</th>
                        </tr>
                      </thead>
                      <tbody>
                        {returnRows.map((r) => (
                          <tr
                            key={r.id}
                            onClick={() =>
                              setDetail({ kind: "return", id: r.id })
                            }
                          >
                            <td>
                              <button
                                className="erp-row-link"
                                onClick={() =>
                                  setDetail({ kind: "return", id: r.id })
                                }
                              >
                                {r.id}
                              </button>
                            </td>
                            <td>
                              <span className="erp-cell-primary">
                                #{r.order_id}
                              </span>
                              <span className="erp-cell-secondary">
                                {name(customerFor(data, r.customer_id))}
                              </span>
                            </td>
                            <td>{r.item_name}</td>
                            <td>{r.reason}</td>
                            <td>
                              <Badge value={r.status} />
                            </td>
                            <td className="number">{money(r.refund_amount)}</td>
                            <td className="erp-muted">{stamp(r.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!returnRows.length && (
                      <Empty
                        title="No returns in this view"
                        text="Create a return for a delivered item to start a request."
                      />
                    )}
                  </div>
                </section>
              )}
              {view === "conversations" && (
                <section className="erp-panel">
                  <div className="erp-list-toolbar">
                    <label className="erp-search">
                      <Search size={16} />
                      <input
                        aria-label="Search conversations"
                        placeholder="Search customer, message, or order"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </label>
                    <span>{conversations.length} conversations</span>
                  </div>
                  <div className="erp-table-wrap">
                    <table className="erp-table">
                      <thead>
                        <tr>
                          <th>Customer</th>
                          <th>Last message</th>
                          <th>Account status</th>
                          <th>Order</th>
                          <th>Messages</th>
                          <th>Updated</th>
                        </tr>
                      </thead>
                      <tbody>
                        {conversations.map((c) => (
                          <tr
                            key={c.reference}
                            onClick={() =>
                              setDetail({
                                kind: "conversation",
                                id: c.reference,
                              })
                            }
                          >
                            <td>
                              <button
                                className="erp-row-link"
                                onClick={() =>
                                  setDetail({
                                    kind: "conversation",
                                    id: c.reference,
                                  })
                                }
                              >
                                {c.customer_name}
                              </button>
                              <span className="erp-cell-secondary">
                                {c.reference}
                              </span>
                            </td>
                            <td>
                              <span className="erp-message-preview">
                                {c.last_message.replaceAll("*", "")}
                              </span>
                            </td>
                            <td>
                              <Badge value={c.stage} />
                              {c.verification_code && (
                                <span className="erp-inline-code">
                                  Code: {c.verification_code}
                                </span>
                              )}
                            </td>
                            <td>{c.order_id ? "#" + c.order_id : "—"}</td>
                            <td>{c.message_count}</td>
                            <td className="erp-muted">{stamp(c.updated_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!conversations.length && (
                      <Empty
                        title="No customer conversations"
                        text="Open the customer chat to start a conversation."
                      />
                    )}
                  </div>
                </section>
              )}
              {view === "support" && (
                <section className="erp-panel">
                  <div className="erp-table-tabs">
                    {["all", "queued", "in_progress", "resolved"].map((s) => (
                      <button
                        key={s}
                        className={filter === s ? "active" : ""}
                        onClick={() => setFilter(s)}
                      >
                        {s === "all" ? "All requests" : labels[s]}
                        <span>
                          {s === "all"
                            ? data.tickets.length
                            : data.tickets.filter((t) => t.status === s).length}
                        </span>
                      </button>
                    ))}
                  </div>
                  <div className="erp-list-toolbar">
                    <label className="erp-search">
                      <Search size={16} />
                      <input
                        aria-label="Search support requests"
                        placeholder="Search requests"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </label>
                    <span>{tickets.length} requests</span>
                  </div>
                  <div className="erp-table-wrap">
                    <table className="erp-table">
                      <thead>
                        <tr>
                          <th>Request</th>
                          <th>Customer question</th>
                          <th>Order</th>
                          <th>Status</th>
                          <th>Assigned to</th>
                          <th>Created</th>
                        </tr>
                      </thead>
                      <tbody>
                        {tickets.map((t) => (
                          <tr
                            key={t.id}
                            onClick={() =>
                              setDetail({ kind: "ticket", id: t.id })
                            }
                          >
                            <td>
                              <button
                                className="erp-row-link"
                                onClick={() =>
                                  setDetail({ kind: "ticket", id: t.id })
                                }
                              >
                                {t.id}
                              </button>
                              <span className="erp-cell-secondary">
                                {t.reason.replaceAll("_", " ")}
                              </span>
                            </td>
                            <td>
                              <span className="erp-message-preview">
                                {t.request}
                              </span>
                            </td>
                            <td>{t.order_id ? "#" + t.order_id : "—"}</td>
                            <td>
                              <Badge value={t.status} />
                            </td>
                            <td>{t.assignee || "Unassigned"}</td>
                            <td className="erp-muted">{stamp(t.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!tickets.length && (
                      <Empty
                        title="No support requests waiting"
                        text="Customer escalations arrive here with their conversation and order context."
                      />
                    )}
                  </div>
                </section>
              )}
              {view === "activity" && (
                <section className="erp-panel">
                  <div className="erp-list-toolbar">
                    <label className="erp-search">
                      <Search size={16} />
                      <input
                        aria-label="Search activity"
                        placeholder="Search activity or record ID"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </label>
                    <span>{data.activity.length} events</span>
                  </div>
                  <div className="erp-table-wrap">
                    <table className="erp-table">
                      <thead>
                        <tr>
                          <th>Time</th>
                          <th>Activity</th>
                          <th>Record</th>
                          <th>Changed by</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.activity
                          .filter((a) =>
                            [a.summary, a.entity_id, a.actor]
                              .join(" ")
                              .toLowerCase()
                              .includes(search.toLowerCase()),
                          )
                          .map((a) => (
                            <tr key={a.id}>
                              <td className="erp-muted">{stamp(a.at)}</td>
                              <td>
                                <strong className="erp-normal-weight">
                                  {a.summary}
                                </strong>
                                {!!Object.keys(a.changes).length && (
                                  <details className="erp-change-details">
                                    <summary>View changes</summary>
                                    <pre>
                                      {JSON.stringify(a.changes, null, 2)}
                                    </pre>
                                  </details>
                                )}
                              </td>
                              <td>
                                <span className="erp-entity-label">
                                  {a.entity}
                                </span>{" "}
                                {a.entity_id}
                              </td>
                              <td>{a.actor}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                    {!data.activity.length && (
                      <Empty
                        title="No changes recorded yet"
                        text="Order edits, customer changes, and return decisions will be logged here."
                      />
                    )}
                  </div>
                </section>
              )}
              {view === "settings" && (
                <div className="erp-settings-grid">
                  <section className="erp-panel">
                    <header>
                      <h2>Customer channel</h2>
                    </header>
                    <div className="erp-settings-content">
                      <div className="erp-setting-row">
                        <div>
                          <strong>Verification method</strong>
                          <p>
                            Demo lookup matches an existing customer contact.
                            Code verification uses the operations inbox.
                          </p>
                        </div>
                        <select
                          aria-label="Customer verification method"
                          value={data.settings.verification_mode}
                          onChange={(e) =>
                            setting("verification_mode", e.target.value)
                          }
                        >
                          <option value="demo_match">
                            Contact match · demo
                          </option>
                          <option value="code">Verification code</option>
                        </select>
                      </div>
                      <div className="erp-setting-row">
                        <div>
                          <strong>Request processing</strong>
                          <p>
                            The rules baseline uses the same order and return
                            tools.
                          </p>
                        </div>
                        <select
                          aria-label="Request processing"
                          value={data.settings.inference_mode}
                          onChange={(e) =>
                            setting("inference_mode", e.target.value)
                          }
                        >
                          <option value="model">Configured AI model</option>
                          <option value="baseline">Rules baseline</option>
                        </select>
                      </div>
                      <div className="erp-setting-note">
                        <MessageSquare size={16} />
                        <span>
                          Customer channel: local WhatsApp mockup. No Meta,
                          email, or SMS service is connected.
                        </span>
                      </div>
                    </div>
                  </section>
                  <section className="erp-panel">
                    <header>
                      <h2>Order connection</h2>
                    </header>
                    <div className="erp-settings-content">
                      {[
                        {
                          key: "order_api_available",
                          label: "Order API",
                          hint: "Turn off to test an unavailable order source.",
                          checked: data.settings.order_api_available,
                        },
                        {
                          key: "feed_health",
                          label: "Carrier feed",
                          hint: "Turn off to simulate delayed delivery updates.",
                          checked: data.settings.feed_health === "healthy",
                        },
                        {
                          key: "ticket_store_available",
                          label: "Support request storage",
                          hint: "Turn off to test a failed handoff.",
                          checked: data.settings.ticket_store_available,
                        },
                      ].map((s) => (
                        <label className="erp-setting-row" key={s.key}>
                          <div>
                            <strong>{s.label}</strong>
                            <p>{s.hint}</p>
                          </div>
                          <input
                            type="checkbox"
                            role="switch"
                            aria-label={s.label}
                            checked={s.checked}
                            onChange={(e) =>
                              setting(
                                s.key,
                                s.key === "feed_health"
                                  ? e.target.checked
                                    ? "healthy"
                                    : "lagging"
                                  : e.target.checked,
                              )
                            }
                          />
                        </label>
                      ))}
                    </div>
                  </section>
                  <section className="erp-panel">
                    <header>
                      <h2>Store</h2>
                    </header>
                    <div className="erp-settings-content">
                      <dl className="erp-facts">
                        <dt>Store name</dt>
                        <dd>Threadline</dd>
                        <dt>Currency</dt>
                        <dd>INR</dd>
                        <dt>Policy timezone</dt>
                        <dd>{data.settings.business_timezone}</dd>
                        <dt>Demo clock</dt>
                        <dd>{day(data.settings.demo_now)}</dd>
                        <dt>Dataset</dt>
                        <dd>Synthetic customers and orders</dd>
                      </dl>
                    </div>
                  </section>
                  <section className="erp-panel">
                    <header>
                      <h2>Sample data</h2>
                    </header>
                    <div className="erp-settings-content">
                      <p className="erp-settings-description">
                        Restore the sample customers and orders. This clears
                        demo conversations, returns, support requests, and the
                        activity log.
                      </p>
                      <button
                        className="erp-button"
                        disabled={busy}
                        onClick={restore}
                      >
                        <RefreshCw size={15} />
                        Restore sample data
                      </button>
                    </div>
                  </section>
                </div>
              )}
            </>
          )}
          <footer className="erp-workspace-footer">
            <span>Threadline Operations</span>
            <span>Local demo workspace · synthetic data</span>
          </footer>
        </main>
      </div>
      {detail && data && (
        <>
          <div className="erp-drawer-scrim" onClick={() => setDetail(null)} />
          <aside
            className="erp-drawer"
            role="dialog"
            aria-modal="true"
            aria-label={recordTitle}
          >
            <header>
              <div>
                <span>
                  {detail.kind === "order"
                    ? "ORDER"
                    : detail.kind === "customer"
                      ? "CUSTOMER"
                      : detail.kind === "return"
                        ? "RETURN"
                        : detail.kind === "ticket"
                          ? "SUPPORT REQUEST"
                          : "CONVERSATION"}
                </span>
                <h2>{recordTitle}</h2>
              </div>
              <button
                className="erp-icon"
                aria-label="Close record"
                onClick={() => setDetail(null)}
              >
                <X size={20} />
              </button>
            </header>
            {selectedOrder && (
              <OrderDetails
                key={selectedOrder.order_id}
                order={selectedOrder}
                customer={customerFor(data, selectedOrder.customer_id)}
                activity={data.activity.filter(
                  (a) =>
                    a.entity === "order" &&
                    a.entity_id === selectedOrder.order_id,
                )}
                save={async (body) => {
                  const result = await mutate<{ order: Order }>(
                    "/orders/" + selectedOrder.order_id,
                    "PATCH",
                    body,
                  );
                  notify("Order updated");
                  return result.order;
                }}
                openCustomer={() =>
                  setDetail({ kind: "customer", id: selectedOrder.customer_id })
                }
                createReturn={() =>
                  setModal({ kind: "return", orderId: selectedOrder.order_id })
                }
              />
            )}
            {selectedCustomer && (
              <CustomerDetails
                customer={selectedCustomer}
                orders={data.orders.filter(
                  (o) => o.customer_id === selectedCustomer.customer_id,
                )}
                edit={() =>
                  setModal({
                    kind: "customer",
                    customerId: selectedCustomer.customer_id,
                  })
                }
                openOrder={(id) => setDetail({ kind: "order", id })}
                newOrder={() =>
                  setModal({
                    kind: "order",
                    customerId: selectedCustomer.customer_id,
                  })
                }
                notify={notify}
              />
            )}
            {selectedReturn && (
              <ReturnDetails
                key={selectedReturn.id}
                record={selectedReturn}
                customer={customerFor(data, selectedReturn.customer_id)}
                save={async (body) => {
                  const next = await mutate<ReturnRecord>(
                    "/returns/" + selectedReturn.id,
                    "PATCH",
                    body,
                  );
                  notify("Return updated");
                  return next;
                }}
                openOrder={() =>
                  setDetail({ kind: "order", id: selectedReturn.order_id })
                }
              />
            )}
            {selectedTicket && (
              <SupportDetails
                key={selectedTicket.id}
                ticket={selectedTicket}
                save={async (body) => {
                  await mutate("/tickets/" + selectedTicket.id, "PATCH", body);
                  notify("Support request saved");
                }}
                openOrder={() =>
                  selectedTicket.order_id &&
                  setDetail({ kind: "order", id: selectedTicket.order_id })
                }
              />
            )}
            {detail.kind === "conversation" && (
              <>
                <div className="erp-detail-summary">
                  <Badge value={conversation?.stage || "contact"} />
                  <button
                    className="erp-text-button danger"
                    onClick={async () => {
                      try {
                        await mutate(
                          "/conversations/" + detail.id + "/reset",
                          "POST",
                        );
                        setDetail(null);
                        notify("Conversation restarted");
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    }}
                  >
                    Restart conversation
                  </button>
                </div>
                <ConversationView record={conversation} />
              </>
            )}
          </aside>
        </>
      )}
      {modal && data && (
        <Modal
          title={
            modal.kind === "customer"
              ? modal.customerId
                ? "Edit customer"
                : "Add customer"
              : modal.kind === "order"
                ? "Create order"
                : modal.kind === "estimate"
                  ? "Delivery estimate · #" + modal.orderId
                  : modal.kind === "return"
                    ? "Create return"
                    : "Demo tools"
          }
          close={() => setModal(null)}
          wide={modal.kind === "order"}
        >
          {modal.kind === "customer" && (
            <CustomerForm
              customer={data.customers.find(
                (c) => c.customer_id === modal.customerId,
              )}
              close={() => setModal(null)}
              submit={async (body) => {
                const c = await mutate<Customer>(
                  "/customers" +
                    (modal.customerId ? "/" + modal.customerId : ""),
                  modal.customerId ? "PATCH" : "POST",
                  body,
                );
                setModal(null);
                setView("customers");
                setSearch("");
                setFilter("all");
                setDetail({ kind: "customer", id: c.customer_id });
                notify(
                  modal.customerId ? "Customer updated" : "Customer created",
                );
              }}
            />
          )}
          {modal.kind === "estimate" &&
            data.orders.find((o) => o.order_id === modal.orderId) && (
              <DeliveryEstimateForm
                key={modal.orderId}
                order={data.orders.find((o) => o.order_id === modal.orderId)!}
                demoNow={data.settings.demo_now}
                close={() => setModal(null)}
                save={async (body) => {
                  const result = await mutate<{ order: Order }>(
                    "/orders/" + modal.orderId,
                    "PATCH",
                    body,
                  );
                  setModal(null);
                  notify("Delivery estimate saved");
                  return result.order;
                }}
              />
            )}
          {modal.kind === "order" && (
            <NewOrderForm
              data={data}
              customerId={modal.customerId}
              initialSize={modal.initialSize}
              close={() => setModal(null)}
              submit={async (body) => {
                const o = await mutate<Order>("/orders", "POST", body);
                setModal(null);
                setView("orders");
                setSearch("");
                setFilter("all");
                setDetail({ kind: "order", id: o.order_id });
                notify("Order #" + o.order_id + " created");
              }}
            />
          )}
          {modal.kind === "return" && (
            <NewReturnForm
              data={data}
              orderId={modal.orderId}
              close={() => setModal(null)}
              submit={async (body) => {
                const r = await mutate<ReturnRecord>("/returns", "POST", body);
                setModal(null);
                setView("returns");
                setSearch("");
                setFilter("all");
                setDetail({ kind: "return", id: r.id });
                notify("Return " + r.id + " created");
              }}
            />
          )}
          {modal.kind === "demo" && (
            <div className="erp-form-content">
              <div className="erp-demo-steps">
                <h3>Run a customer conversation</h3>
                <ol>
                  <li>Open the customer chat in a separate tab.</li>
                  <li>
                    Ask about an order and use <code>aarav@example.com</code>.
                  </li>
                  <li>Select order #4812, then change its status here.</li>
                  <li>
                    Use its Delivery estimate cell to change the date, then ask
                    “When will it arrive?” in chat.
                  </li>
                  <li>
                    The chat receives the saved order update automatically.
                  </li>
                </ol>
                <a
                  className="erp-button primary"
                  href="/whatsapp"
                  target="_blank"
                  rel="noreferrer"
                >
                  <MessageSquare size={15} />
                  Open customer chat
                  <ExternalLink size={12} />
                </a>
              </div>
              <div className="erp-demo-shortcuts">
                <button
                  onClick={() => {
                    setModal(null);
                    navigate("customers");
                  }}
                >
                  <Users size={18} />
                  <span>
                    Add a customer
                    <small>Use a new email or phone in the chat.</small>
                  </span>
                  <ChevronRight size={15} />
                </button>
                <button onClick={() => setModal({ kind: "order" })}>
                  <ShoppingBag size={18} />
                  <span>
                    Create an order
                    <small>
                      New purchases appear on the customer's account.
                    </small>
                  </span>
                  <ChevronRight size={15} />
                </button>
                <button
                  onClick={() =>
                    setModal({
                      kind: "order",
                      customerId: "demo-customer-a",
                      initialSize: "S",
                    })
                  }
                >
                  <ShoppingBag size={18} />
                  <span>
                    Prepare a size-change demo
                    <small>
                      Create an unfulfilled S order for Aarav. Ask to change it
                      to M in chat.
                    </small>
                  </span>
                  <ChevronRight size={15} />
                </button>
                <button
                  onClick={() => {
                    setModal(null);
                    navigate("settings");
                  }}
                >
                  <SettingsIcon size={18} />
                  <span>
                    Connection & verification settings
                    <small>
                      Test unavailable data or enable code verification.
                    </small>
                  </span>
                  <ChevronRight size={15} />
                </button>
              </div>
            </div>
          )}
        </Modal>
      )}
      {toast && (
        <div className="erp-toast" role="status">
          <Check size={16} />
          {toast}
          <button
            aria-label="Dismiss notification"
            onClick={() => setToast("")}
          >
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
