import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowUpRight,
  Check,
  ChevronRight,
  Copy,
  LoaderCircle,
  Plus,
  Save,
  Trash2,
  X,
} from "lucide-react";
import type {
  Customer,
  Order,
  ReturnRecord,
  Ticket,
  Workspace,
  Activity,
  ConversationDetail,
} from "./erp-types";
import { day, labels, money, name, stamp } from "./erp-types";

export function Badge({ value }: { value: string }) {
  return (
    <span className={"erp-badge badge-" + value}>
      <i />
      {labels[value] || value.replaceAll("_", " ")}
    </span>
  );
}
export function Empty({ title, text }: { title: string; text?: string }) {
  return (
    <div className="erp-empty">
      <span className="erp-empty-icon">—</span>
      <strong>{title}</strong>
      {text && <p>{text}</p>}
    </div>
  );
}
export function Modal({
  title,
  children,
  close,
  wide = false,
}: {
  title: string;
  children: React.ReactNode;
  close: () => void;
  wide?: boolean;
}) {
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "Tab") {
        const all = document.querySelectorAll<HTMLElement>(
          ".erp-modal button:not(:disabled),.erp-modal input,.erp-modal select,.erp-modal textarea",
        );
        const first = all[0],
          last = all[all.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="erp-modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <section
        className={"erp-modal " + (wide ? "wide" : "")}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header>
          <h2>{title}</h2>
          <button
            className="erp-icon"
            onClick={close}
            aria-label="Close dialog"
            autoFocus
          >
            <X size={19} />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}

export function CustomerForm({
  customer,
  submit,
  close,
}: {
  customer?: Customer;
  submit: (body: unknown) => Promise<void>;
  close: () => void;
}) {
  const [form, setForm] = useState({
    first_name: customer?.first_name || "",
    last_name: customer?.last_name || "",
    email: customer?.email || "",
    phone: customer?.phone || "",
    city: customer?.city || "",
    notes: customer?.notes || "",
  });
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await submit(form);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save}>
      <div className="erp-form-content">
        <div className="erp-form-grid">
          <label>
            First name
            <input
              required
              maxLength={60}
              value={form.first_name}
              onChange={(e) => setForm({ ...form, first_name: e.target.value })}
            />
          </label>
          <label>
            Last name
            <input
              maxLength={60}
              value={form.last_name}
              onChange={(e) => setForm({ ...form, last_name: e.target.value })}
            />
          </label>
          <label>
            Email address
            <input
              required
              type="email"
              value={form.email}
              placeholder="customer@example.com"
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </label>
          <label>
            Phone number
            <input
              required
              type="tel"
              value={form.phone}
              placeholder="+1 202 555 0100"
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </label>
          <label className="full">
            City / region
            <input
              value={form.city}
              placeholder="Austin, TX"
              onChange={(e) => setForm({ ...form, city: e.target.value })}
            />
          </label>
          <label className="full">
            Internal notes
            <textarea
              rows={3}
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </label>
        </div>
        {error && (
          <p className="erp-form-error" role="alert">
            {error}
          </p>
        )}
      </div>
      <footer className="erp-form-actions">
        <button className="erp-button" type="button" onClick={close}>
          Cancel
        </button>
        <button className="erp-button primary" disabled={busy}>
          {busy ? (
            <LoaderCircle size={15} className="spin" />
          ) : (
            <Save size={15} />
          )}{" "}
          {customer ? "Save customer" : "Create customer"}
        </button>
      </footer>
    </form>
  );
}

export function NewOrderForm({
  data,
  customerId,
  submit,
  close,
}: {
  data: Workspace;
  customerId?: string;
  submit: (body: unknown) => Promise<void>;
  close: () => void;
}) {
  const [cid, setCid] = useState(
      customerId || data.customers[0]?.customer_id || "",
    ),
    [city, setCity] = useState(
      data.customers.find(
        (c) => c.customer_id === (customerId || data.customers[0]?.customer_id),
      )?.city || "",
    );
  const [lines, setLines] = useState([
      { sku: data.catalog[0]?.sku || "", quantity: 1, size: "M" },
    ]),
    [payment, setPayment] = useState("paid"),
    [notes, setNotes] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const total = lines.reduce(
    (sum, l) =>
      sum +
      (data.catalog.find((p) => p.sku === l.sku)?.price || 0) * l.quantity,
    0,
  );
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await submit({
        customer_id: cid,
        shipping_city: city,
        payment_status: payment,
        notes,
        items: lines,
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save}>
      <div className="erp-form-content">
        <div className="erp-form-grid">
          <label>
            Customer
            <select
              required
              value={cid}
              onChange={(e) => {
                setCid(e.target.value);
                setCity(
                  data.customers.find((c) => c.customer_id === e.target.value)
                    ?.city || "",
                );
              }}
            >
              {data.customers.map((c) => (
                <option value={c.customer_id} key={c.customer_id}>
                  {name(c)} · {c.email}
                </option>
              ))}
            </select>
          </label>
          <label>
            Payment status
            <select
              value={payment}
              onChange={(e) => setPayment(e.target.value)}
            >
              <option value="paid">Paid</option>
              <option value="pending">Payment pending</option>
            </select>
          </label>
          <label className="full">
            Delivery city / region
            <input
              required
              value={city}
              onChange={(e) => setCity(e.target.value)}
            />
          </label>
        </div>
        <div className="erp-form-section">
          <h3>Order items</h3>
          {lines.map((line, i) => (
            <div className="erp-order-line-form" key={i}>
              <label className="product">
                Product
                <select
                  value={line.sku}
                  onChange={(e) =>
                    setLines(
                      lines.map((l, n) =>
                        n === i ? { ...l, sku: e.target.value } : l,
                      ),
                    )
                  }
                >
                  {data.catalog.map((p) => (
                    <option value={p.sku} key={p.sku}>
                      {p.name} · {money(p.price)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Size
                <select
                  value={line.size}
                  onChange={(e) =>
                    setLines(
                      lines.map((l, n) =>
                        n === i ? { ...l, size: e.target.value } : l,
                      ),
                    )
                  }
                >
                  {["XS", "S", "M", "L", "XL", "32", "34"].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
              <label>
                Qty
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={line.quantity}
                  onChange={(e) =>
                    setLines(
                      lines.map((l, n) =>
                        n === i
                          ? { ...l, quantity: Number(e.target.value) }
                          : l,
                      ),
                    )
                  }
                />
              </label>
              <button
                type="button"
                className="erp-icon"
                disabled={lines.length === 1}
                aria-label="Remove order item"
                onClick={() => setLines(lines.filter((_, n) => n !== i))}
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
          <button
            type="button"
            className="erp-text-button"
            onClick={() =>
              setLines([
                ...lines,
                { sku: data.catalog[0].sku, size: "M", quantity: 1 },
              ])
            }
          >
            <Plus size={14} />
            Add item
          </button>
          <div className="erp-order-total">
            <span>Total</span>
            <strong>{money(total)}</strong>
          </div>
        </div>
        <label className="erp-field">
          Internal note
          <textarea
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>
        {error && (
          <p className="erp-form-error" role="alert">
            {error}
          </p>
        )}
      </div>
      <footer className="erp-form-actions">
        <button className="erp-button" type="button" onClick={close}>
          Cancel
        </button>
        <button className="erp-button primary" disabled={busy}>
          {busy ? (
            <LoaderCircle className="spin" size={15} />
          ) : (
            <Plus size={15} />
          )}
          Create order
        </button>
      </footer>
    </form>
  );
}

const orderFields = (o: Order) => ({
  status: o.status,
  carrier_eta_date: o.carrier_eta_date || "",
  carrier: o.carrier || "",
  tracking_reference: o.tracking_reference || "",
  shipping_city: o.shipping_city || "",
  payment_status: o.payment_status || "paid",
  priority: o.priority || "normal",
  notes: o.notes || "",
});
export function OrderDetails({
  order,
  customer,
  activity,
  save,
  openCustomer,
  createReturn,
}: {
  order: Order;
  customer?: Customer;
  activity: Activity[];
  save: (body: unknown) => Promise<Order>;
  openCustomer: () => void;
  createReturn: () => void;
}) {
  const [form, setForm] = useState(orderFields(order)),
    [base, setBase] = useState(orderFields(order)),
    [revision, setRevision] = useState(order.revision || 1),
    [tab, setTab] = useState("details"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [saved, setSaved] = useState(false);
  const dirty = JSON.stringify(form) !== JSON.stringify(base);
  const changed = (order.revision || 1) !== revision;
  function reload() {
    setForm(orderFields(order));
    setBase(orderFields(order));
    setRevision(order.revision || 1);
    setError("");
  }
  useEffect(() => {
    if (!dirty && changed) reload();
  }, [order.revision]);
  const field = (key: keyof typeof form, value: string) => {
    setForm({ ...form, [key]: value });
    setSaved(false);
  };
  async function updateItem(itemId: string, status: string) {
    setBusy(true);
    setError("");
    try {
      const next = await save({
        item_statuses: [{ item_id: itemId, status }],
        revision,
      });
      setForm(orderFields(next));
      setBase(orderFields(next));
      setRevision(next.revision || 1);
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function commit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const next = await save({
        ...form,
        carrier_eta_date: form.carrier_eta_date || null,
        revision,
      });
      setForm(orderFields(next));
      setBase(orderFields(next));
      setRevision(next.revision || 1);
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="erp-detail-summary">
        <Badge value={order.status} />
        <span>
          {day(order.ordered_at)} · {money(order.order_total)}
        </span>
        {order.priority === "high" && (
          <span className="erp-priority">High priority</span>
        )}
      </div>
      <div className="erp-detail-tabs">
        <button
          className={tab === "details" ? "active" : ""}
          onClick={() => setTab("details")}
        >
          Details
        </button>
        <button
          className={tab === "timeline" ? "active" : ""}
          onClick={() => setTab("timeline")}
        >
          Timeline <span>{activity.length}</span>
        </button>
      </div>
      {tab === "timeline" ? (
        <div className="erp-drawer-content">
          <ActivityList rows={activity} />
        </div>
      ) : (
        <form className="erp-detail-form" onSubmit={commit}>
          <div className="erp-drawer-content">
            {changed && dirty && (
              <div className="erp-inline-warning">
                This record changed in another tab.
                <button type="button" onClick={reload}>
                  Reload current record
                </button>
              </div>
            )}
            <section className="erp-detail-section">
              <header>
                <h3>Customer</h3>
                <button
                  className="erp-text-button"
                  type="button"
                  onClick={openCustomer}
                >
                  View profile
                  <ArrowUpRight size={13} />
                </button>
              </header>
              <div className="erp-person">
                <span className="erp-avatar">
                  {customer?.first_name[0] || "?"}
                </span>
                <div>
                  <strong>{name(customer)}</strong>
                  <span>{customer?.email}</span>
                  <span>{customer?.phone}</span>
                </div>
              </div>
            </section>
            <section className="erp-detail-section">
              <header>
                <h3>
                  Items <span>{order.items.length}</span>
                </h3>
                <button
                  type="button"
                  className="erp-text-button"
                  onClick={createReturn}
                >
                  Create return
                  <ChevronRight size={13} />
                </button>
              </header>
              <div className="erp-line-items">
                {order.items.map((item) => (
                  <div key={item.item_id}>
                    <span className="erp-item-icon">
                      {item.image ? (
                        <img src={item.image} alt={item.name} />
                      ) : (
                        item.name
                          .split(" ")
                          .map((w) => w[0])
                          .slice(0, 2)
                          .join("")
                      )}
                    </span>
                    <div>
                      <strong>{item.name}</strong>
                      <small>
                        {item.size || "—"} / {item.color || "—"} · Qty{" "}
                        {item.quantity}
                        {item.returned ? " · Returned" : ""}
                      </small>
                      <select
                        className="erp-item-status"
                        aria-label={`Delivery status for ${item.name}`}
                        value={item.status}
                        disabled={
                          busy ||
                          dirty ||
                          item.returned ||
                          order.status === "cancelled"
                        }
                        onChange={(e) =>
                          void updateItem(item.item_id, e.target.value)
                        }
                      >
                        {[
                          "processing",
                          "in_transit",
                          "delivered",
                          ...(item.returned ? ["returned"] : []),
                          ...(item.status === "cancelled" ? ["cancelled"] : []),
                        ].map((s) => (
                          <option value={s} key={s}>
                            {labels[s]}
                          </option>
                        ))}
                      </select>
                    </div>
                    <span>
                      {item.unit_price
                        ? money(item.unit_price * item.quantity)
                        : "—"}
                    </span>
                  </div>
                ))}
              </div>
              <div className="erp-detail-total">
                <span>Order total</span>
                <strong>{money(order.order_total)}</strong>
              </div>
            </section>
            <section className="erp-detail-section">
              <header>
                <h3>Fulfilment</h3>
                <span className="erp-muted">
                  Revision {order.revision || 1}
                </span>
              </header>
              <div className="erp-form-grid">
                <label>
                  Fulfilment status
                  <select
                    value={form.status}
                    onChange={(e) => field("status", e.target.value)}
                  >
                    {[
                      "processing",
                      "in_transit",
                      "partially_delivered",
                      "delivered",
                      "cancelled",
                    ].map((s) => (
                      <option value={s} key={s}>
                        {labels[s]}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Estimated delivery
                  <input
                    type="date"
                    disabled={form.status === "delivered"}
                    value={form.carrier_eta_date}
                    onChange={(e) => field("carrier_eta_date", e.target.value)}
                  />
                </label>
                <label>
                  Carrier
                  <input
                    value={form.carrier}
                    onChange={(e) => field("carrier", e.target.value)}
                  />
                </label>
                <label>
                  Tracking reference
                  <input
                    value={form.tracking_reference}
                    onChange={(e) =>
                      field("tracking_reference", e.target.value)
                    }
                  />
                </label>
                <label className="full">
                  Delivery city / region
                  <input
                    value={form.shipping_city}
                    onChange={(e) => field("shipping_city", e.target.value)}
                  />
                </label>
                <label>
                  Payment
                  <select
                    value={form.payment_status}
                    onChange={(e) => field("payment_status", e.target.value)}
                  >
                    {["paid", "pending", "partially_refunded", "refunded"].map(
                      (s) => (
                        <option value={s} key={s}>
                          {labels[s]}
                        </option>
                      ),
                    )}
                  </select>
                </label>
                <label>
                  Priority
                  <select
                    value={form.priority}
                    onChange={(e) => field("priority", e.target.value)}
                  >
                    <option value="normal">Normal</option>
                    <option value="high">High</option>
                  </select>
                </label>
              </div>
            </section>
            <label className="erp-field">
              Internal notes
              <textarea
                value={form.notes}
                rows={3}
                onChange={(e) => field("notes", e.target.value)}
              />
              <small>Visible to your operations team.</small>
            </label>
            <p className="erp-record-meta">
              Last updated {stamp(order.source_updated_at)} ·{" "}
              {order.policy_version}
            </p>
            {error && (
              <p className="erp-form-error" role="alert">
                {error}
              </p>
            )}
          </div>
          <footer className="erp-drawer-save">
            <span>
              {saved ? (
                <>
                  <Check size={14} />
                  Changes saved
                </>
              ) : dirty ? (
                "Unsaved changes"
              ) : (
                "All changes saved"
              )}
            </span>
            <button className="erp-button primary" disabled={!dirty || busy}>
              {busy ? (
                <LoaderCircle className="spin" size={15} />
              ) : (
                <Save size={15} />
              )}
              Save changes
            </button>
          </footer>
        </form>
      )}
    </>
  );
}

export function ActivityList({ rows }: { rows: Activity[] }) {
  return rows.length ? (
    <div className="erp-timeline">
      {rows.map((a) => (
        <div key={a.id}>
          <i />
          <div>
            <strong>{a.summary}</strong>
            <p>
              {a.actor} · {stamp(a.at)}
            </p>
            {!!Object.keys(a.changes).length && (
              <details>
                <summary>View changes</summary>
                <pre>{JSON.stringify(a.changes, null, 2)}</pre>
              </details>
            )}
          </div>
        </div>
      ))}
    </div>
  ) : (
    <Empty
      title="No activity recorded"
      text="Changes to this record will appear here."
    />
  );
}

export function NewReturnForm({
  data,
  orderId,
  submit,
  close,
}: {
  data: Workspace;
  orderId?: string;
  submit: (body: unknown) => Promise<void>;
  close: () => void;
}) {
  const eligible = data.orders.filter((o) =>
    o.items.some((i) => i.delivered_at),
  );
  const [selected, setSelected] = useState(
    orderId && eligible.some((o) => o.order_id === orderId)
      ? orderId
      : eligible[0]?.order_id || "",
  );
  const order = data.orders.find((o) => o.order_id === selected);
  const [item, setItem] = useState(
    order?.items.find((i) => i.delivered_at)?.item_id || "",
  );
  const [reason, setReason] = useState("Wrong size"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await submit({ order_id: selected, item_id: item, reason, quantity: 1 });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save}>
      <div className="erp-form-content">
        <div className="erp-form-grid">
          <label className="full">
            Order
            <select
              required
              value={selected}
              onChange={(e) => {
                setSelected(e.target.value);
                setItem(
                  data.orders
                    .find((o) => o.order_id === e.target.value)
                    ?.items.find((i) => i.delivered_at)?.item_id || "",
                );
              }}
            >
              {eligible.map((o) => (
                <option key={o.order_id} value={o.order_id}>
                  #{o.order_id} ·{" "}
                  {name(
                    data.customers.find((c) => c.customer_id === o.customer_id),
                  )}
                </option>
              ))}
            </select>
          </label>
          <label className="full">
            Item
            <select
              required
              value={item}
              onChange={(e) => setItem(e.target.value)}
            >
              {order?.items
                .filter((i) => i.delivered_at)
                .map((i) => (
                  <option key={i.item_id} value={i.item_id}>
                    {i.name} · {i.size}
                  </option>
                ))}
            </select>
          </label>
          <label className="full">
            Return reason
            <select value={reason} onChange={(e) => setReason(e.target.value)}>
              {[
                "Wrong size",
                "Damaged item",
                "Changed mind",
                "Wrong item received",
                "Other",
              ].map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </label>
        </div>
        {error && (
          <p className="erp-form-error" role="alert">
            {error}
          </p>
        )}
      </div>
      <footer className="erp-form-actions">
        <button className="erp-button" type="button" onClick={close}>
          Cancel
        </button>
        <button className="erp-button primary" disabled={busy || !item}>
          {busy ? (
            <LoaderCircle size={15} className="spin" />
          ) : (
            <Plus size={15} />
          )}
          Create return
        </button>
      </footer>
    </form>
  );
}

export function ReturnDetails({
  record,
  customer,
  save,
  openOrder,
}: {
  record: ReturnRecord;
  customer?: Customer;
  save: (body: unknown) => Promise<ReturnRecord>;
  openOrder: () => void;
}) {
  const [notes, setNotes] = useState(record.notes),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [pickupDate, setPickupDate] = useState(record.pickup_date || "");
  const [pickupRef, setPickupRef] = useState(record.pickup_reference || "");
  const [inspection, setInspection] = useState(record.inspection || "pending");
  const [refundRef, setRefundRef] = useState(record.refund_reference || "");
  const [publicReason, setPublicReason] = useState(record.public_reason || "");
  const [baseUpdated, setBaseUpdated] = useState(record.updated_at);
  const changed = baseUpdated !== record.updated_at;
  function reloadReturn() {
    setNotes(record.notes);
    setPickupDate(record.pickup_date || "");
    setPickupRef(record.pickup_reference || "");
    setInspection(record.inspection || "pending");
    setRefundRef(record.refund_reference || "");
    setPublicReason(record.public_reason || "");
    setBaseUpdated(record.updated_at);
    setError("");
  }
  const transitions: Record<string, { value: string; label: string }[]> = {
    requested: [
      { value: "approved", label: "Approve return" },
      { value: "declined", label: "Decline return" },
    ],
    approved: [
      { value: "pickup_scheduled", label: "Confirm pickup booking" },
      { value: "declined", label: "Decline return" },
    ],
    pickup_scheduled: [
      { value: "received", label: "Mark received for inspection" },
    ],
    received: [
      { value: "refunded", label: "Record refund" },
      { value: "declined", label: "Decline after inspection" },
    ],
    declined: [{ value: "requested", label: "Reopen request" }],
    refunded: [],
  };
  async function update(status: string) {
    setBusy(true);
    try {
      const next = await save({
        status,
        notes,
        updated_at: baseUpdated,
        pickup_date: pickupDate || null,
        pickup_reference: pickupRef,
        inspection,
        refund_reference: refundRef,
        public_reason: publicReason,
      });
      setBaseUpdated(next.updated_at);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="erp-drawer-content">
      {changed && !busy && (
        <div className="erp-inline-warning">
          This return changed in another tab.
          <button type="button" onClick={reloadReturn}>
            Reload current record
          </button>
        </div>
      )}
      <div className="erp-detail-summary">
        <Badge value={record.status} />
        <span>{stamp(record.created_at)}</span>
      </div>
      <section className="erp-detail-section">
        <h3>Return details</h3>
        <dl className="erp-facts">
          <dt>Order</dt>
          <dd>
            <button className="erp-text-button" onClick={openOrder}>
              #{record.order_id}
              <ArrowUpRight size={13} />
            </button>
          </dd>
          <dt>Customer</dt>
          <dd>{name(customer)}</dd>
          <dt>Item</dt>
          <dd>{record.item_name}</dd>
          <dt>Quantity</dt>
          <dd>{record.quantity}</dd>
          <dt>Reason</dt>
          <dd>{record.reason}</dd>
          <dt>Refund value</dt>
          <dd>{money(record.refund_amount)}</dd>
          {record.source && (
            <>
              <dt>Submitted through</dt>
              <dd>{record.source}</dd>
            </>
          )}
          {record.condition && (
            <>
              <dt>Customer condition</dt>
              <dd>{record.condition}</dd>
              <dt>Product tags</dt>
              <dd>{record.tags}</dd>
            </>
          )}
          {record.pickup_address && (
            <>
              <dt>Pickup address</dt>
              <dd>{record.pickup_address}</dd>
              <dt>Preferred window</dt>
              <dd>{record.pickup_preference}</dd>
            </>
          )}
          {record.pickup_reference && (
            <>
              <dt>Booking</dt>
              <dd>
                {record.pickup_date} · {record.pickup_reference}
              </dd>
            </>
          )}
          {record.refund_reference && (
            <>
              <dt>Refund reference</dt>
              <dd>{record.refund_reference}</dd>
            </>
          )}
        </dl>
      </section>
      {!!record.photos?.length && (
        <section className="erp-detail-section">
          <h3>
            Customer photos <span>{record.photos.length}</span>
          </h3>
          <div className="erp-return-photos">
            {record.photos.map((p) => (
              <a href={p.url} target="_blank" rel="noreferrer" key={p.id}>
                <img src={p.url} alt="Customer supplied return evidence" />
              </a>
            ))}
          </div>
          <p className="erp-muted">
            Evidence received. Review the garment, tag, and any reported damage.
          </p>
        </section>
      )}
      {record.review_required && record.status === "requested" && (
        <div className="erp-inline-warning">
          Review required: condition, tags, or missing photos need a staff
          decision.
        </div>
      )}
      <div className="erp-return-steps">
        {[
          "requested",
          "approved",
          "pickup_scheduled",
          "received",
          "refunded",
        ].map((step, i) => (
          <div
            key={step}
            className={
              [
                "requested",
                "approved",
                "pickup_scheduled",
                "received",
                "refunded",
              ].indexOf(record.status) >= i
                ? "complete"
                : ""
            }
          >
            <span>{i + 1}</span>
            {labels[step]}
          </div>
        ))}
      </div>
      {record.status === "approved" && (
        <section className="erp-detail-section">
          <h3>Confirm carrier booking</h3>
          <p className="erp-muted">
            Record an existing booking. This demo does not book a carrier.
          </p>
          <div className="erp-form-grid">
            <label>
              Pickup date
              <input
                type="date"
                value={pickupDate}
                onChange={(e) => setPickupDate(e.target.value)}
              />
            </label>
            <label>
              Carrier booking reference
              <input
                value={pickupRef}
                placeholder="e.g. DEMO-PU-1042"
                onChange={(e) => setPickupRef(e.target.value)}
              />
            </label>
          </div>
        </section>
      )}
      {record.status === "received" && (
        <section className="erp-detail-section">
          <h3>Inspection & refund</h3>
          <div className="erp-form-grid">
            <label>
              Inspection result
              <select
                value={inspection}
                onChange={(e) => setInspection(e.target.value)}
              >
                <option value="pending">Pending inspection</option>
                <option value="passed">Passed</option>
                <option value="failed">Failed</option>
              </select>
            </label>
            <label>
              Recorded refund reference
              <input
                value={refundRef}
                placeholder="Payment / refund reference"
                onChange={(e) => setRefundRef(e.target.value)}
              />
            </label>
          </div>
          <p className="erp-muted">
            Recording a refund updates this demo ledger. It does not transfer
            money.
          </p>
        </section>
      )}
      <label className="erp-field">
        Internal notes
        <textarea
          rows={4}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </label>
      {["requested", "approved", "received"].includes(record.status) && (
        <label className="erp-field">
          Reason visible to customer{" "}
          <span className="erp-muted">Required if declining</span>
          <input
            value={publicReason}
            maxLength={200}
            placeholder="Explain the decision and next step"
            onChange={(e) => setPublicReason(e.target.value)}
          />
        </label>
      )}
      {error && (
        <p className="erp-form-error" role="alert">
          {error}
        </p>
      )}
      <div className="erp-inline-actions">
        {transitions[record.status]?.map((action, i) => (
          <button
            className={"erp-button " + (i === 0 ? "primary" : "")}
            key={action.value}
            disabled={
              busy ||
              changed ||
              (action.value === "pickup_scheduled" &&
                (!pickupDate || !pickupRef.trim())) ||
              (action.value === "refunded" &&
                (inspection !== "passed" || !refundRef.trim())) ||
              (action.value === "declined" && !publicReason.trim())
            }
            onClick={() => update(action.value)}
          >
            {action.label}
          </button>
        ))}
        <button
          className="erp-button"
          disabled={busy || changed || notes === record.notes}
          onClick={() => update(record.status)}
        >
          Save note
        </button>
      </div>
      {record.status === "refunded" && (
        <p className="erp-muted">
          Refund recorded in the sample order system. No payment service is
          connected.
        </p>
      )}
    </div>
  );
}

export function SupportDetails({
  ticket,
  save,
  openOrder,
}: {
  ticket: Ticket;
  save: (body: unknown) => Promise<void>;
  openOrder: () => void;
}) {
  const [form, setForm] = useState({
      status: ticket.status,
      assignee: ticket.assignee || "Unassigned",
      internal_note: ticket.internal_note || "",
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function commit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await save(form);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={commit}>
      <div className="erp-drawer-content">
        <div className="erp-detail-summary">
          <Badge value={ticket.status} />
          <span>{stamp(ticket.created_at)}</span>
        </div>
        <div className="erp-request-quote">{ticket.request}</div>
        <dl className="erp-facts">
          <dt>Reason</dt>
          <dd>{ticket.reason.replaceAll("_", " ")}</dd>
          <dt>Order</dt>
          <dd>
            {ticket.order_id ? (
              <button
                type="button"
                className="erp-text-button"
                onClick={openOrder}
              >
                #{ticket.order_id}
                <ArrowUpRight size={13} />
              </button>
            ) : (
              "General enquiry"
            )}
          </dd>
        </dl>
        <div className="erp-form-grid">
          <label>
            Status
            <select
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
            >
              {["queued", "in_progress", "resolved"].map((s) => (
                <option value={s} key={s}>
                  {labels[s]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Assigned to
            <select
              value={form.assignee}
              onChange={(e) => setForm({ ...form, assignee: e.target.value })}
            >
              <option>Unassigned</option>
              <option>Support team</option>
              <option>Store manager</option>
            </select>
          </label>
          <label className="full">
            Internal note
            <textarea
              rows={3}
              value={form.internal_note}
              onChange={(e) =>
                setForm({ ...form, internal_note: e.target.value })
              }
            />
          </label>
        </div>
        <h3 className="erp-section-label">Conversation</h3>
        <div className="erp-transcript">
          {ticket.transcript.map((m, i) => (
            <div key={i}>
              <span>{m.role === "user" ? "Customer" : "Assistant"}</span>
              <p>{m.content}</p>
            </div>
          ))}
        </div>
        {error && (
          <p className="erp-form-error" role="alert">
            {error}
          </p>
        )}
      </div>
      <footer className="erp-drawer-save">
        <span>{ticket.id}</span>
        <button className="erp-button primary" disabled={busy}>
          <Save size={15} />
          Save request
        </button>
      </footer>
    </form>
  );
}

export function ConversationView({
  record,
}: {
  record: ConversationDetail | null;
}) {
  return record ? (
    <div className="erp-drawer-content">
      {record.verification_code && (
        <div className="erp-code-box">
          <span>Demo verification code</span>
          <strong>{record.verification_code}</strong>
          <small>Local verification only; no message is sent externally.</small>
        </div>
      )}
      <div className="erp-conversation-thread">
        {record.messages.map((m) => (
          <div key={m.id} className={m.role === "user" ? "out" : "in"}>
            {m.media && (
              <img
                className="erp-conversation-photo"
                src={m.media.url}
                alt="Return photo from customer"
              />
            )}
            {m.product && (
              <div className="erp-conversation-product">
                {m.product.image && (
                  <img src={m.product.image} alt={m.product.name} />
                )}
                <div>
                  <strong>{m.product.name}</strong>
                  <small>
                    {m.product.variant} · {money(m.product.amount)}
                  </small>
                </div>
              </div>
            )}
            <span>
              {m.role === "user" ? "Customer" : "Threadline"} · {stamp(m.at)}
            </span>
            <p>{m.text.replaceAll("*", "")}</p>
          </div>
        ))}
      </div>
      {record.latest_trace && (
        <details className="erp-trace">
          <summary>Response evidence</summary>
          <pre>{JSON.stringify(record.latest_trace, null, 2)}</pre>
        </details>
      )}
    </div>
  ) : (
    <div className="erp-loading">
      <LoaderCircle className="spin" size={20} />
      Loading conversation…
    </div>
  );
}

export async function copyContact(value: string) {
  await navigator.clipboard.writeText(value);
}
export function CustomerDetails({
  customer,
  orders,
  edit,
  openOrder,
  newOrder,
  notify,
}: {
  customer: Customer;
  orders: Order[];
  edit: () => void;
  openOrder: (id: string) => void;
  newOrder: () => void;
  notify: (s: string) => void;
}) {
  return (
    <div className="erp-drawer-content">
      <div className="erp-customer-profile">
        <span className="erp-avatar large">
          {customer.first_name[0]}
          {customer.last_name?.[0] || ""}
        </span>
        <h2>{name(customer)}</h2>
        <span>{customer.display_id || customer.customer_id}</span>
      </div>
      <div className="erp-inline-actions">
        <button className="erp-button" onClick={edit}>
          Edit customer
        </button>
        <button className="erp-button primary" onClick={newOrder}>
          <Plus size={14} />
          New order
        </button>
      </div>
      <dl className="erp-facts">
        <dt>Email</dt>
        <dd>
          {customer.email}
          <button
            className="erp-icon small"
            aria-label="Copy customer email"
            onClick={() =>
              copyContact(customer.email).then(() => notify("Email copied"))
            }
          >
            <Copy size={13} />
          </button>
        </dd>
        <dt>Phone</dt>
        <dd>
          {customer.phone}
          <button
            className="erp-icon small"
            aria-label="Copy customer phone"
            onClick={() =>
              copyContact(customer.phone).then(() => notify("Phone copied"))
            }
          >
            <Copy size={13} />
          </button>
        </dd>
        <dt>Location</dt>
        <dd>{customer.city || "—"}</dd>
        <dt>Customer since</dt>
        <dd>{day(customer.created_at)}</dd>
        <dt>Total spent</dt>
        <dd>
          {money(
            orders
              .filter((o) => o.status !== "cancelled")
              .reduce((n, o) => n + o.order_total, 0),
          )}
        </dd>
      </dl>
      <section className="erp-detail-section">
        <header>
          <h3>
            Orders <span>{orders.length}</span>
          </h3>
        </header>
        {orders.length ? (
          <div className="erp-related-orders">
            {orders.map((o) => (
              <button key={o.order_id} onClick={() => openOrder(o.order_id)}>
                <strong>#{o.order_id}</strong>
                <span>{day(o.ordered_at)}</span>
                <Badge value={o.status} />
                <ChevronRight size={14} />
              </button>
            ))}
          </div>
        ) : (
          <Empty
            title="No orders yet"
            text="Create an order for this customer to try the WhatsApp lookup."
          />
        )}
      </section>
      {customer.notes && (
        <section className="erp-detail-section">
          <h3>Internal notes</h3>
          <p>{customer.notes}</p>
        </section>
      )}
    </div>
  );
}
