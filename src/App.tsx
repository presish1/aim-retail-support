import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowRight, ArrowUp, Check, CheckCheck, ChevronDown, CircleHelp, Clock3, Code2, Database, ExternalLink, Inbox, LoaderCircle, MessageCircle, Package, RefreshCw, RotateCcw, ShieldCheck, Shirt, Terminal, Unplug, UserRound, X } from 'lucide-react'
import type { Message, ModelHealth, Order, Reply, Studio, Ticket, Trace } from './types'

type View = 'desk' | 'orders' | 'inbox'
const labels: Record<string, string> = { in_transit: 'In transit', delivered: 'Delivered', processing: 'Processing', partially_delivered: 'Partially delivered', cancelled: 'Cancelled' }
const displayDate = (value: string | null | undefined) => value ? new Date(value.length === 10 ? value + 'T12:00:00Z' : value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }) : 'Not available'
const displayTime = (value: string | undefined) => value ? new Date(value).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) + ' UTC' : 'Not checked'
const humanize = (value: string) => value.toLowerCase().replaceAll('_', ' ')

async function request<T>(path: string, options: RequestInit = {}, token?: string, admin?: string): Promise<T> {
  const response = await fetch('/api' + path, { ...options, headers: { 'Content-Type': 'application/json', ...(token ? { 'X-Demo-Session': token } : {}), ...(admin ? { 'X-Demo-Admin': admin } : {}), ...options.headers } })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : body.detail?.message || `Request failed (${response.status}).`)
  }
  return response.json()
}

function Status({ value }: { value: string }) { return <span className={'status status-' + value}><span />{labels[value] || humanize(value)}</span> }
function ThreadMark({ small = false }: { small?: boolean }) { return <span className={'thread-mark' + (small ? ' small' : '')} aria-hidden="true">t<span>·</span></span> }

function Evidence({ trace }: { trace: Trace }) {
  const [open, setOpen] = useState(false)
  return <section className="evidence">
    <button className="evidence-summary" aria-expanded={open} onClick={() => setOpen(!open)}><span><Code2 size={16} /> Inspect this answer <span className="trace-mode">{trace.mode === 'model' ? 'Qwen tool call' : trace.mode === 'baseline_fallback' ? 'Rules fallback' : 'Rules baseline'}</span></span><span>{(trace.latency_ms / 1000).toFixed(2)}s <ChevronDown size={15} className={open ? 'rotate' : ''} /></span></button>
    {open && <div className="evidence-content"><div className="trace-grid">{trace.steps.map((step, i) => <div key={i} className="trace-step"><span className={'step-dot ' + step.state}>{step.state === 'passed' ? <Check size={12} /> : <Unplug size={12} />}</span><div><strong>{step.name}</strong><p>{step.detail}</p></div></div>)}</div><div className="trace-meta"><span>{trace.model || 'No model inference'}</span><span>{trace.usage.input_tokens} input / {trace.usage.output_tokens} output tokens</span><span>{trace.id}</span></div>{trace.proposal && <details><summary>Tool proposal & source evidence</summary><pre>{JSON.stringify({ proposal: trace.proposal, evidence: trace.evidence || null }, null, 2)}</pre></details>}</div>}
  </section>
}

function ResultCard({ reply }: { reply: Reply }) {
  const card = reply.card
  if (!card) return null
  if (card.type === 'order') return <div className="result-card"><div className="result-top"><span className="eyebrow">ORDER #{card.order_id}</span><Status value={card.status} /></div><div className="result-product"><div className="product-thumb"><Shirt size={32} strokeWidth={1.2} /></div><div><strong>{card.items[0].name}</strong><span>{card.items.length > 1 ? `${card.items.length} items · ` : ''}{card.carrier}</span></div></div><div className="result-facts"><span>Estimated arrival<strong>{card.status === 'delivered' ? 'Delivered' : displayDate(card.carrier_eta_date)}</strong></span><span>Carrier / system update<strong>{displayDate(card.source_updated_at)} · {displayTime(card.source_updated_at)}</strong></span></div><div className="source-line"><Database size={12} /> Fresh order-system read · {displayTime(card.fetched_at)}</div></div>
  if (card.type === 'return') return <div className={'result-card return-card decision-' + card.decision}><div className="result-top"><span className="eyebrow">RETURN CHECK · #{card.order_id}</span><ShieldCheck size={18} /></div><strong>{card.item_name}</strong><div className="return-decision">{card.reason}</div><div className="result-facts"><span>Request deadline<strong>{displayDate(card.deadline)}</strong></span><span>Policy version<strong>{card.policy_version}</strong></span></div><div className="source-line">Initial eligibility only · no refund or return has been approved</div></div>
  return <div className="result-card ticket-card"><div className="result-top"><span className="eyebrow">SUPPORT REQUEST</span><Inbox size={18} /></div><strong className="ticket-reference">{card.id}</strong><p>{humanize(card.reason)}</p><div className="source-line"><CheckCheck size={14} /> Saved to the agent inbox with context</div></div>
}

function OrderEditor({ order, admin, onSaved }: { order: Order; admin: string; onSaved: () => void }) {
  const [status, setStatus] = useState(order.status)
  const [eta, setEta] = useState(order.carrier_eta_date || '')
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  useEffect(() => { setStatus(order.status); setEta(order.carrier_eta_date || ''); setNotice('') }, [order.status, order.carrier_eta_date])
  const dirty = status !== order.status || eta !== (order.carrier_eta_date || '')
  async function save(e: FormEvent) {
    e.preventDefault(); setSaving(true); setNotice('')
    try { await request('/studio/orders/' + order.order_id, { method: 'PATCH', body: JSON.stringify({ status, carrier_eta_date: eta || null }) }, undefined, admin); onSaved(); setNotice('Saved to SQLite. Ask the assistant again to see the change.') }
    catch (e) { setNotice((e as Error).message) } finally { setSaving(false) }
  }
  return <form className="order-editor" onSubmit={save}><div className="order-editor-heading"><div className={'product-thumb color-' + (Number(order.order_id) % 3)}><Shirt size={34} strokeWidth={1.2} /></div><div><span className="eyebrow">ORDER #{order.order_id}</span><h3>{order.items[0].name}</h3><p>{order.customer_id === 'demo-customer-a' ? 'Customer A' : 'Customer B'} · {order.items.length} {order.items.length === 1 ? 'item' : 'items'}</p></div><Status value={order.status} /></div><div className="editor-fields"><label>Order status<select value={status} onChange={e => setStatus(e.target.value)}>{Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label>Carrier estimate<input type="date" aria-label={'Carrier estimate for order ' + order.order_id} value={eta} onChange={e => setEta(e.target.value)} disabled={status === 'delivered'} /></label><button className="button primary" disabled={!dirty || saving}>{saving ? <LoaderCircle size={16} className="spin" /> : <Database size={16} />}{saving ? 'Saving…' : 'Save record'}</button></div>{notice && <p className="save-notice" role="status">{notice}</p>}<div className="editor-bottom"><span>Source updated {displayDate(order.source_updated_at)} · {displayTime(order.source_updated_at)}</span><span>{order.policy_version}</span></div></form>
}

function TicketDetail({ ticket }: { ticket: Ticket }) {
  return <div className="ticket-detail"><div className="ticket-detail-head"><span className="eyebrow">{ticket.id} / QUEUED FOR REVIEW</span><span className="reason-badge">{humanize(ticket.reason)}</span></div><h2>All the context.<br /><em>One place.</em></h2><div className="ticket-request">“{ticket.request}”</div><div className="ticket-facts"><span>Order<strong>{ticket.order_id ? '#' + ticket.order_id : 'General enquiry'}</strong></span><span>Identity<strong>{humanize(ticket.verification)}</strong></span><span>Source status<strong>{ticket.source_failure ? humanize(ticket.source_failure) : ticket.evidence ? 'Verified context attached' : 'No order lookup'}</strong></span><span>Policy<strong>{ticket.evidence?.policy_version || 'Not available'}</strong></span></div><p className="queue-note"><Clock3 size={16} />{ticket.queue_message}</p><h3>Conversation handed over</h3><div className="transcript">{ticket.transcript.map((m, i) => <div key={i}><span>{m.role === 'user' ? 'Customer' : 'Assistant'}</span><p>{m.content}</p></div>)}</div></div>
}

export default function App() {
  const [view, setView] = useState<View>('desk')
  const [studio, setStudio] = useState<Studio | null>(null)
  const [health, setHealth] = useState<ModelHealth | null>(null)
  const [admin, setAdmin] = useState('')
  const [session, setSession] = useState('')
  const [persona, setPersona] = useState('a')
  const [mode, setMode] = useState<'model' | 'baseline'>('model')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [activeOrder, setActiveOrder] = useState('4812')
  const [activeTicket, setActiveTicket] = useState('')
  const [guide, setGuide] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [controlBusy, setControlBusy] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const sending = useRef(false)
  const refresh = useCallback(async (key: string) => {
    const next = await request<Studio>('/studio/state', {}, undefined, key)
    setStudio(next)
  }, [])
  const updateHealth = useCallback(async () => { const data = await request<{ model: ModelHealth }>('/health'); setHealth(data.model) }, [])
  useEffect(() => {
    let alive = true
    request<{ admin_key: string }>('/studio/bootstrap').then(async data => { if (alive) { setAdmin(data.admin_key); await refresh(data.admin_key) } }).catch(e => { if (alive) setError(e.message) })
    updateHealth().catch(() => {})
    const timer = setInterval(() => updateHealth().catch(() => {}), 20000)
    return () => { alive = false; clearInterval(timer) }
  }, [refresh, updateHealth])
  useEffect(() => {
    if (!admin) return
    const update = () => { if (document.visibilityState === 'visible') refresh(admin).catch(() => {}) }
    update()
    window.addEventListener('focus', update)
    document.addEventListener('visibilitychange', update)
    return () => { window.removeEventListener('focus', update); document.removeEventListener('visibilitychange', update) }
  }, [view, admin, refresh])
  useEffect(() => {
    let alive = true
    setSession(''); setMessages([]); setError('')
    request<{ session_id: string }>('/session', { method: 'POST', body: JSON.stringify({ persona }) }).then(data => { if (alive) setSession(data.session_id) }).catch(e => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [persona])
  useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }) }, [messages, busy])
  useEffect(() => {
    if (!guide) return
    const previous = document.activeElement as HTMLElement | null
    const fn = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setGuide(false)
      if (e.key === 'Tab') {
        const controls = document.querySelectorAll<HTMLElement>('.guide-modal button, .guide-modal a')
        const first = controls[0], last = controls[controls.length - 1]
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus() }
        if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus() }
      }
    }
    window.addEventListener('keydown', fn)
    return () => { window.removeEventListener('keydown', fn); previous?.focus() }
  }, [guide])

  async function send(text: string) {
    if (!text.trim() || !session || sending.current) return
    sending.current = true; setBusy(true); setError(''); setInput('')
    setMessages(old => [...old, { id: crypto.randomUUID(), role: 'user', text }])
    try {
      const reply = await request<Reply>('/chat', { method: 'POST', body: JSON.stringify({ message: text, mode }) }, session)
      setMessages(old => [...old, { id: reply.trace.id, role: 'assistant', text: reply.message, reply }])
      if (admin) await refresh(admin)
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false); sending.current = false; inputRef.current?.focus() }
  }
  async function control(key: string, value: boolean | string) {
    if (controlBusy) return
    setControlBusy(true)
    const previous = studio
    setStudio(old => old ? { ...old, settings: { ...old.settings, [key]: value } } : old)
    try { await request('/studio/controls', { method: 'PATCH', body: JSON.stringify({ [key]: value }) }, undefined, admin); await refresh(admin) }
    catch (e) { setStudio(previous); setError((e as Error).message) }
    finally { setControlBusy(false) }
  }
  async function reset() {
    setResetting(true)
    try { await request('/studio/reset', { method: 'POST' }, undefined, admin); setMessages([]); setActiveTicket(''); await refresh(admin) } catch (e) { setError((e as Error).message) } finally { setResetting(false) }
  }
  const owned = studio?.orders.filter(o => o.customer_id === 'demo-customer-' + persona) || []
  const selectedTicket = studio?.tickets.find(t => t.id === activeTicket) || studio?.tickets[0]
  const currentOrder = owned.find(o => o.order_id === activeOrder) || owned[0]
  const lastReply = [...messages].reverse().find(m => m.reply)?.reply

  return <div className="app-shell">
    <header className="site-header"><a href="#" className="wordmark" onClick={e => { e.preventDefault(); setView('desk') }} aria-label="Threadline home"><ThreadMark />Threadline<span className="wordmark-period">.</span></a><div className="header-description">ORDER & RETURNS STUDIO<span>AI in Management · Scenario A</span></div><div className="header-right"><a className="wa-launch" href="/whatsapp" target="_blank" rel="noreferrer"><MessageCircle size={15} />WhatsApp demo<ExternalLink size={12} /></a><span className="synthetic-label"><span />Synthetic data</span><a className="icon-button repo-link" href="https://github.com/presish1/aim-retail-support" target="_blank" rel="noreferrer" aria-label="Open project repository"><ExternalLink size={17} /></a><button className="icon-button" aria-label="How the prototype works" onClick={() => setGuide(true)}><CircleHelp size={19} /></button></div></header>
    <nav className="view-nav" aria-label="Prototype views"><div>{([{ id: 'desk', title: 'Customer desk', num: '01', icon: MessageCircle }, { id: 'orders', title: 'Order system', num: '02', icon: Database }, { id: 'inbox', title: 'Agent inbox', num: '03', icon: Inbox }] as const).map(tab => <button key={tab.id} onClick={() => setView(tab.id)} aria-current={view === tab.id ? 'page' : undefined} className={view === tab.id ? 'nav-active' : ''}><span className="nav-num">{tab.num}</span><tab.icon size={16} /><span>{tab.title}</span>{tab.id === 'inbox' && !!studio?.tickets.length && <span className="count">{studio.tickets.length}</span>}</button>)}</div><span className="demo-date"><Clock3 size={13} />Demo clock · 7 Nov 2026</span></nav>
    <main>
      <div className="page-intro"><div><span className="eyebrow">{view === 'desk' ? 'THE POST-PURCHASE EXPERIENCE' : view === 'orders' ? 'THE SOURCE OF TRUTH' : 'WHEN A HUMAN MAKES THE DIFFERENCE'}</span><h1>{view === 'desk' ? <>A little clarity.<br className="mobile-break" /><em> A lot less waiting.</em></> : view === 'orders' ? <>Change the record.<em> See the difference.</em></> : <>Thoughtful handoffs.<em> Better resolutions.</em></>}</h1></div><p>{view === 'desk' ? 'A current answer to the everyday questions.\nA real person for everything that needs one.' : view === 'orders' ? 'Update the synthetic order system, then ask again.\nEvery answer starts with a fresh source read.' : 'Questions, order facts, and attempted steps.\nReady for your team to pick up.'}</p></div>
      {error && <div className="global-error" role="alert"><Unplug size={17} /><span>{error}</span><button className="icon-button" onClick={() => setError('')} aria-label="Dismiss error"><X size={16} /></button></div>}
      {view === 'desk' && <div className="desk-layout">
        <aside className="customer-sidebar"><div className="sidebar-heading"><span className="eyebrow">DEMO CUSTOMER</span><ShieldCheck size={16} /></div><label className="customer-select"><UserRound size={18} /><select aria-label="Simulated customer identity" value={persona} disabled={busy} onChange={e => setPersona(e.target.value)}><option value="a">Customer A · verified</option><option value="b">Customer B · verified</option><option value="guest">Unverified visitor</option></select></label><p className="simulation-note">Simulated verification for this classroom demo.</p><div className="orders-list-heading"><h2>Your orders</h2><span>{owned.length}</span></div><div className="orders-list">{owned.map(order => <button key={order.order_id} className={'order-choice ' + (currentOrder?.order_id === order.order_id ? 'selected' : '')} onClick={() => setActiveOrder(order.order_id)}><div className={'product-thumb color-' + (Number(order.order_id) % 3)}><Shirt size={27} strokeWidth={1.15} /></div><div><span>#{order.order_id}</span><strong>{order.items[0].name}</strong><Status value={order.status} /></div><ArrowRight size={15} /></button>)}</div>{persona === 'guest' && <div className="guest-note"><ShieldCheck size={25} /><p>Select a verified demo customer to access orders. An order number alone does not grant access.</p></div>}<div className="sidebar-bottom"><span className="eyebrow">BUILT AROUND TRUST</span><p>The order system supplies the facts.<br />Business rules check the return.<br />People make the exceptions.</p><button className="text-button" onClick={() => setGuide(true)}>Explore the service design <ArrowRight size={14} /></button></div></aside>
        <section className="chat-panel" aria-label="Customer support conversation"><div className="chat-header"><div><span className="availability-dot" /><strong>Threadline care</strong><span>Here to help, around the clock</span></div><span className="assistant-badge">Automated assistant</span></div><div className="chat-scroll" ref={scrollRef}><div className="welcome"><ThreadMark /><span className="eyebrow">A GOOD PLACE TO START</span><h2>Let's take care<br />of your <em>order.</em></h2><p>Track a delivery, check a return, or find the right person.<br />We'll start with the facts.</p><div className="welcome-actions"><button disabled={busy || !session} onClick={() => send(currentOrder ? `Where is order #${currentOrder.order_id}?` : 'Where is my order?')}><Package size={17} /><span>Track my order</span><ArrowRight size={15} /></button><button disabled={busy || !session} onClick={() => send(`Can I return an item from order #${owned.find(o => o.order_id === '4813')?.order_id || currentOrder?.order_id || ''}?`)}><RotateCcw size={17} /><span>Check a return</span><ArrowRight size={15} /></button><button disabled={busy || !session} onClick={() => send('I want to talk to support.')}><UserRound size={17} /><span>Talk to a person</span><ArrowRight size={15} /></button></div></div>
          <div className="messages" role="log" aria-live="polite" aria-label="Conversation messages">{messages.map(message => <div key={message.id} className={'message-row ' + message.role}>{message.role === 'assistant' && <ThreadMark small />}<div className="message-content">{message.role === 'assistant' && <span className="message-author">THREADLINE</span>}<div className="message-bubble">{message.text}</div>{message.reply?.trace.note && <div className="fallback-note"><Unplug size={13} />{message.reply.trace.note}</div>}{message.reply && <ResultCard reply={message.reply} />}{message.reply && message.reply.actions.length > 0 && <div className="reply-actions">{message.reply.actions.map(action => <button key={action.text} disabled={busy} onClick={() => send(action.text)}>{action.label}<ArrowRight size={13} /></button>)}</div>}{message.reply && <Evidence trace={message.reply.trace} />}</div></div>)}{busy && <div className="message-row assistant"><ThreadMark small /><div className="checking" role="status"><span /><span /><span /><span>{mode === 'model' ? 'Understanding your request & checking the source' : 'Checking the order system'}</span></div></div>}<div ref={bottom} /></div>
        </div><div className="chat-composer"><form onSubmit={e => { e.preventDefault(); send(input) }}><label className="sr-only" htmlFor="message">Your message</label><input id="message" ref={inputRef} value={input} maxLength={2000} onChange={e => setInput(e.target.value)} placeholder="Ask about your order…" disabled={busy || !session} autoComplete="off" /><button type="submit" disabled={!input.trim() || busy || !session} aria-label="Send message">{busy ? <LoaderCircle size={19} className="spin" /> : <ArrowUp size={20} />}</button></form><div className="composer-note"><ShieldCheck size={12} />Answers use current order records. Exceptions go to a person.</div></div></section>
      </div>}
      {view === 'orders' && <div className="system-layout"><section className="system-orders"><div className="section-title"><div><span className="eyebrow">API-BACKED SYNTHETIC ORDERS</span><h2>A small system. <em>A real connection.</em></h2></div><button className="button subtle" onClick={() => refresh(admin)}><RefreshCw size={15} />Refresh</button></div><div className="system-intro"><Database size={18} /><p>Records persist in SQLite. Customer tools can read owned orders; only this evaluator console can edit them.</p></div>{studio?.orders.map(order => <OrderEditor key={order.order_id} order={order} admin={admin} onSaved={() => refresh(admin)} />)}</section><aside className="demo-controls"><span className="eyebrow">PROVE IT IN THE ROOM</span><h2>Change a fact.<br /><em>Ask again.</em></h2><ol><li>Ask about order #4812.</li><li>Change its status to Delivered.</li><li>Save, then ask “Can you check again?”</li></ol><button className="button primary" onClick={() => setView('desk')}>Back to customer desk<ArrowRight size={16} /></button><div className="controls-divider" /><h3>Test the uncomfortable bits.</h3><p>A trustworthy service handles missing information honestly.</p><label className="toggle-row"><span><strong>Order API</strong><small>{studio?.settings.order_api_available ? 'Available for fresh reads' : 'Unavailable — answers must stop'}</small></span><input aria-label="Order API available" disabled={controlBusy} type="checkbox" role="switch" checked={studio?.settings.order_api_available ?? true} onChange={e => control('order_api_available', e.target.checked)} /></label><label className="toggle-row"><span><strong>Carrier feed</strong><small>{studio?.settings.feed_health === 'healthy' ? 'Healthy source connection' : 'Known delay in delivery data'}</small></span><input aria-label="Carrier feed healthy" disabled={controlBusy} type="checkbox" role="switch" checked={studio?.settings.feed_health === 'healthy'} onChange={e => control('feed_health', e.target.checked ? 'healthy' : 'lagging')} /></label><label className="toggle-row"><span><strong>Ticket storage</strong><small>{studio?.settings.ticket_store_available ? 'Can save support requests' : 'Simulate failed handoff writes'}</small></span><input aria-label="Ticket storage available" disabled={controlBusy} type="checkbox" role="switch" checked={studio?.settings.ticket_store_available ?? true} onChange={e => control('ticket_store_available', e.target.checked)} /></label><div className="controls-divider" /><button className="button reset-button" disabled={resetting || busy} onClick={reset}><RotateCcw size={15} />{resetting ? 'Restoring…' : 'Restore demo fixtures'}</button><p className="small-note">Restores orders and clears demo conversations, tickets, and traces.</p></aside></div>}
      {view === 'inbox' && <div className="inbox-layout"><aside className="ticket-list"><div className="orders-list-heading"><h2>Needs a person</h2><span>{studio?.tickets.length || 0}</span></div>{studio?.tickets.length ? studio.tickets.map(ticket => <button className={'ticket-choice ' + (selectedTicket?.id === ticket.id ? 'selected' : '')} key={ticket.id} onClick={() => setActiveTicket(ticket.id)}><div><span>{ticket.id}</span><span className="ticket-queued">Queued</span></div><strong>{humanize(ticket.reason)}</strong><p>{ticket.request}</p><small>{ticket.order_id ? '#' + ticket.order_id : 'General enquiry'} · {displayTime(ticket.created_at)}</small></button>) : <div className="empty-list"><Inbox size={27} /><p>No requests waiting.<br />Create a handoff from the customer desk.</p></div>}</aside>{selectedTicket ? <TicketDetail ticket={selectedTicket} /> : <div className="empty-inbox"><div className="empty-icon"><Inbox size={40} strokeWidth={1.1} /></div><span className="eyebrow">READY WHEN YOU'RE NEEDED</span><h2>Some things deserve<br /><em>a human touch.</em></h2><p>When a customer needs a person, their question,<br />verified order facts, and attempted steps arrive here.</p><button className="button primary" onClick={() => { setView('desk'); send('Please ask support to review my late return for order #4814.') }}>Try an exception handoff <ArrowRight size={16} /></button></div>}</div>}
      <section className="runtime-bar" aria-label="Prototype runtime"><div><span className={'runtime-dot ' + (health?.ready ? 'online' : '')} /><strong>{health?.ready ? 'Qwen3-8B connected' : 'Qwen3-8B not connected'}</strong><span>{health?.provider === 'ollama' ? 'Local Ollama' : health?.provider || 'Checking runtime'}</span></div><label>Request mode<select aria-label="Request processing mode" value={mode} disabled={busy} onChange={e => setMode(e.target.value as 'model' | 'baseline')}><option value="model">Qwen3-8B · non-thinking</option><option value="baseline">Rules baseline · no AI</option></select></label><span className={'api-state ' + (studio?.settings.order_api_available ? '' : 'unavailable')}><Database size={13} />Order API {studio?.settings.order_api_available ? 'available' : 'unavailable'}</span>{lastReply && <span className="last-run">Last: {lastReply.trace.mode === 'model' ? 'Qwen' : 'rules'} · {(lastReply.trace.latency_ms / 1000).toFixed(2)}s</span>}</section>
    </main><footer className="site-footer"><span>THREADLINE / SERVICE BY DESIGN</span><span>Academic prototype · fictional retailer · illustrative return policy</span><a href="https://github.com/presish1/aim-retail-support" target="_blank" rel="noreferrer">Project notes <ArrowRight size={12} /></a></footer>
    {guide && <div className="modal-backdrop" onClick={() => setGuide(false)}><section className="guide-modal" role="dialog" aria-modal="true" aria-labelledby="guide-title" onClick={e => e.stopPropagation()}><button className="icon-button modal-close" onClick={() => setGuide(false)} aria-label="Close guide" autoFocus><X size={21} /></button><span className="eyebrow">SCENARIO A / THE DEMONSTRATION</span><h2 id="guide-title">A service you can<br /><em>look inside.</em></h2><p>This local prototype uses a real database and a real model connection. All customer records and policies are fictional.</p><div className="guide-steps"><div><MessageCircle size={21} /><span><strong>01 / Ask naturally</strong>Qwen3-8B selects an allowed tool. The rules baseline is available for comparison.</span></div><div><Database size={21} /><span><strong>02 / Change the source</strong>Update an order in the console. Ask again and watch the answer follow the saved record.</span></div><div><Inbox size={21} /><span><strong>03 / Hand over thoughtfully</strong>Exceptions become saved tickets with context. Refunds and policy exceptions require people.</span></div></div><div className="guide-caveat"><Terminal size={17} /><span>Local classroom mode. Customer selectors simulate verification; no real retailer, WhatsApp account, or production identity system is connected.</span></div><button className="button primary" onClick={() => setGuide(false)}>Explore the prototype <ArrowRight size={16} /></button></section></div>}
  </div>
}
