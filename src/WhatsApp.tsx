import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { ArrowRight, ArrowUp, BadgeCheck, BatteryFull, Camera, Check, CheckCheck, ChevronDown, ChevronLeft, Clock3, Copy, Database, Keyboard, Mail, MessageCircle, Mic, Moon, Phone, Plus, RefreshCw, Send, ShieldCheck, Signal, Smartphone, Sticker, Sun, Video, Wifi, X } from 'lucide-react'
import type { Action, ModelHealth, Trace } from './types'
import './whatsapp.css'

type Delivery = 'sending' | 'delivered' | 'read'
interface ChatMessage { id: string; role: 'user' | 'assistant'; text: string; at: string; actions?: Action[]; in_reply_to?: string; delivery?: Delivery }
interface ChannelState { type: string; session_id?: string; stage?: string; messages?: ChatMessage[]; message?: ChatMessage | string; id?: string; active?: boolean; latest_trace?: Trace | null; selected_order?: string | null; order_id?: string; customer_name?: string | null }
interface DemoInbox { code: string | null; recipient: string | null; expires_in: number }
type Sheet = 'contact' | 'attachments' | 'call' | null
const STORAGE_KEY = 'threadline.whatsapp.session.v1'
const formatTime = (value: string) => new Date(value).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })

function WhatsAppText({ text }: { text: string }) {
  return <>{text.split(/(\*[^*\n]+\*)/g).map((part, i) => part.startsWith('*') && part.endsWith('*') ? <strong key={i}>{part.slice(1, -1)}</strong> : <span key={i}>{part}</span>)}</>
}

function Bubble({ message, onAction, disabled, grouped }: { message: ChatMessage; onAction: (text: string) => void; disabled: boolean; grouped: boolean }) {
  const outgoing = message.role === 'user'
  return <div className={'wa-message-row ' + (outgoing ? 'wa-out' : 'wa-in') + (grouped ? ' wa-grouped' : '')}>
    <div className="wa-bubble"><div className="wa-bubble-body"><WhatsAppText text={message.text} /><span className="wa-time-space" aria-hidden="true">{outgoing ? '00:00 ✓✓' : '00:00'}</span><span className="wa-message-time">{formatTime(message.at)}{outgoing && (message.delivery === 'sending' ? <Clock3 size={11} /> : <CheckCheck size={17} strokeWidth={1.65} className={message.delivery === 'read' ? 'wa-read' : ''} />)}</span></div>{!!message.actions?.length && <div className="wa-business-actions">{message.actions.map(action => <button key={action.text} disabled={disabled} onClick={() => onAction(action.text)}><ArrowUp size={16} className="wa-action-arrow" />{action.label}</button>)}</div>}</div>
  </div>
}

function IOSKeyboard({ onKey, onClose, onSend }: { onKey: (key: string) => void; onClose: () => void; onSend: () => void }) {
  const [caps, setCaps] = useState(true)
  const [numbers, setNumbers] = useState(false)
  const rows = numbers ? ['1234567890', '-/:;()$&@"', '.,?!\''] : ['qwertyuiop', 'asdfghjkl', 'zxcvbnm']
  return <div className="wa-keyboard" aria-label="iPhone demo keyboard"><div className="wa-keyboard-predictions"><span>I</span><span>The</span><span>Thanks</span></div>{rows.map((row, i) => <div className={'wa-key-row wa-key-row-' + i} key={i}>{i === 2 && <button className="wa-key-shift" onClick={() => setCaps(!caps)} aria-label="Shift"><ArrowUp size={20} fill={caps ? 'currentColor' : 'none'} /></button>}{row.split('').map(key => <button key={key} onClick={() => { onKey(caps && !numbers ? key.toUpperCase() : key); setCaps(false) }}>{caps && !numbers ? key.toUpperCase() : key}</button>)}{i === 2 && <button className="wa-key-delete" onClick={() => onKey('BACKSPACE')} aria-label="Delete"><span>⌫</span></button>}</div>)}<div className="wa-key-bottom"><button onClick={() => setNumbers(!numbers)}>{numbers ? 'ABC' : '123'}</button><button className="wa-key-space" onClick={() => onKey(' ')}>space</button><button className="wa-key-return" onClick={onSend}>send</button></div><div className="wa-keyboard-bottom"><button aria-label="Hide demo keyboard" onClick={onClose}><Keyboard size={22} /></button><button aria-label="Voice input information" onClick={() => onKey('VOICE')}><Mic size={23} /></button></div></div>
}

export default function WhatsAppDemo() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [connection, setConnection] = useState<'connecting' | 'connected' | 'reconnecting'>('connecting')
  const [session, setSession] = useState('')
  const [stage, setStage] = useState('contact')
  const [typing, setTyping] = useState(false)
  const [busy, setBusy] = useState(false)
  const [trace, setTrace] = useState<Trace | null>(null)
  const [health, setHealth] = useState<ModelHealth | null>(null)
  const [inbox, setInbox] = useState<DemoInbox | null>(null)
  const [phoneScale, setPhoneScale] = useState(1)
  const [keyboard, setKeyboard] = useState(false)
  const [dark, setDark] = useState(false)
  const [sheet, setSheet] = useState<Sheet>(null)
  const [chatList, setChatList] = useState(false)
  const [error, setError] = useState('')
  const [sourceNotice, setSourceNotice] = useState('')
  const [accountName, setAccountName] = useState<string | null>(null)
  const [orderId, setOrderId] = useState<string | null>(null)
  const [mode, setMode] = useState<'model' | 'baseline'>('model')
  const [showSecond, setShowSecond] = useState(false)
  const [now, setNow] = useState(new Date())
  const socket = useRef<WebSocket | null>(null)
  const pending = useRef(new Map<string, { id: string; text: string; mode: string }>())
  const admin = useRef('')
  const sessionRef = useRef('')
  const busyRef = useRef(false)
  const composer = useRef<HTMLTextAreaElement>(null)
  const deviceStage = useRef<HTMLElement>(null)
  const scroll = useRef<HTMLDivElement>(null)
  const reconnectRef = useRef<() => void>(() => {})

  const loadInbox = useCallback(async (token: string) => {
    if (!token) return
    try {
      if (!admin.current) { const response = await fetch('/api/studio/bootstrap'); admin.current = (await response.json()).admin_key }
      let response = await fetch('/api/studio/whatsapp', { headers: { 'X-Demo-Admin': admin.current, 'X-Demo-Session': token } })
      if (response.status === 403) {
        const fresh = await fetch('/api/studio/bootstrap')
        admin.current = (await fresh.json()).admin_key
        response = await fetch('/api/studio/whatsapp', { headers: { 'X-Demo-Admin': admin.current, 'X-Demo-Session': token } })
      }
      if (response.ok) setInbox(await response.json())
    } catch { /* The chat remains usable if the evaluator inbox is temporarily unavailable. */ }
  }, [])

  useEffect(() => {
    let disposed = false
    let retry: ReturnType<typeof setTimeout>
    let attempts = 0
    function connect() {
      if (disposed) return
      const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/whatsapp/ws`)
      socket.current = ws
      ws.onopen = () => {
        if (disposed) { ws.close(); return }
        attempts = 0
        ws.send(JSON.stringify({ type: 'resume', session_id: localStorage.getItem(STORAGE_KEY) }))
      }
      ws.onmessage = event => {
        if (disposed) return
        let data: ChannelState
        try { data = JSON.parse(event.data) } catch { return }
        if (data.type === 'session') {
          const token = data.session_id!
          sessionRef.current = token; setSession(token); localStorage.setItem(STORAGE_KEY, token)
          setConnection('connected'); setError(''); setStage(data.stage || 'contact')
          setAccountName(data.customer_name || null); setOrderId(data.selected_order || null)
          setTrace(data.latest_trace || null)
          const server = (data.messages || []).map(m => ({ ...m, delivery: 'read' as Delivery }))
          for (const m of server) if (m.in_reply_to) pending.current.delete(m.in_reply_to)
          const serverIds = new Set(server.map(m => m.id))
          const unsent = [...pending.current.values()].filter(m => !serverIds.has(m.id)).map(m => ({ id: m.id, role: 'user' as const, text: m.text, at: new Date().toISOString(), delivery: 'sending' as Delivery }))
          setMessages([...server, ...unsent]); setBusy(pending.current.size > 0); busyRef.current = pending.current.size > 0
          setTyping(pending.current.size > 0)
          for (const request of pending.current.values()) ws.send(JSON.stringify({ type: 'message', ...request }))
          loadInbox(token)
        } else if (data.type === 'ack') {
          setMessages(old => old.map(m => m.id === data.id ? { ...m, delivery: 'delivered' } : m))
        } else if (data.type === 'typing') {
          setTyping(!!data.active)
          if (data.active) setMessages(old => old.map(m => m.role === 'user' && m.delivery !== 'sending' ? { ...m, delivery: 'read' } : m))
        } else if (data.type === 'message' && typeof data.message === 'object') {
          const message = data.message
          if (message.in_reply_to) pending.current.delete(message.in_reply_to)
          setMessages(old => old.some(m => m.id === message.id) ? old : [...old.map(m => m.id === message.in_reply_to ? { ...m, delivery: 'read' as Delivery } : m), message])
          setTyping(false); setBusy(false); busyRef.current = false
          setStage(data.stage || 'contact'); setTrace(data.latest_trace || null)
          if (data.customer_name) setAccountName(data.customer_name)
          setOrderId(data.selected_order || null); setSourceNotice('')
          loadInbox(sessionRef.current)
          if (!window.matchMedia('(pointer: coarse)').matches) composer.current?.focus()
        } else if (data.type === 'source_changed') {
          setSourceNotice(data.order_id ? `Order #${data.order_id} changed in the live system. Ask the store again.` : 'The live order connection changed. Ask again to check the current source.')
        } else if (data.type === 'reset_required') {
          localStorage.removeItem(STORAGE_KEY); pending.current.clear(); ws.close()
        } else if (data.type === 'error') {
          setError(typeof data.message === 'string' ? data.message : 'The channel hit a problem. Please reconnect.'); setBusy(false); busyRef.current = false; setTyping(false)
        }
      }
      ws.onerror = () => setConnection('reconnecting')
      ws.onclose = () => {
        if (disposed) return
        setConnection('reconnecting'); setTyping(false)
        retry = setTimeout(connect, Math.min(1000 * 2 ** attempts++, 8000))
      }
    }
    connect()
    reconnectRef.current = () => { clearTimeout(retry); socket.current?.close() }
    const ping = setInterval(() => { if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify({ type: 'ping' })) }, 25000)
    return () => { disposed = true; clearTimeout(retry); clearInterval(ping); socket.current?.close() }
  }, [loadInbox])

  useEffect(() => {
    const previousTitle = document.title
    document.title = 'Threadline · WhatsApp customer chat'
    return () => { document.title = previousTitle }
  }, [])
  useEffect(() => {
    const resize = () => {
      const mobile = innerWidth < 700
      const width = deviceStage.current?.clientWidth || innerWidth - 40
      setPhoneScale(Math.max(.4, Math.min(1, (innerHeight - (mobile ? 105 : 145)) / 876, (width - 8) / 417)))
    }
    resize(); window.addEventListener('resize', resize)
    const observer = new ResizeObserver(resize)
    if (deviceStage.current) observer.observe(deviceStage.current)
    return () => { window.removeEventListener('resize', resize); observer.disconnect() }
  }, [])
  useEffect(() => {
    const check = async () => { try { const response = await fetch('/api/health'); const data = await response.json(); setHealth(data.model) } catch { setHealth(null) } }
    check(); const interval = setInterval(check, 20000)
    return () => clearInterval(interval)
  }, [])
  useEffect(() => { const timer = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(timer) }, [])
  useEffect(() => { if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight }, [messages, typing, keyboard, chatList])
  useEffect(() => { if (composer.current) { composer.current.style.height = '0px'; composer.current.style.height = Math.min(104, Math.max(23, composer.current.scrollHeight)) + 'px' } }, [input])
  useEffect(() => { if (!sheet) return; const close = (e: KeyboardEvent) => { if (e.key === 'Escape') setSheet(null) }; window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close) }, [sheet])

  function send(text = input) {
    if (!text.trim() || busyRef.current || socket.current?.readyState !== WebSocket.OPEN || !session) return
    const request = { id: crypto.randomUUID(), text: text.trim(), mode }
    pending.current.set(request.id, request); busyRef.current = true; setBusy(true); setInput(''); setSheet(null); setChatList(false)
    setMessages(old => [...old, { id: request.id, role: 'user', text: request.text, at: new Date().toISOString(), delivery: 'sending' }])
    socket.current.send(JSON.stringify({ type: 'message', ...request }))
  }
  function newConversation() {
    if (busy || socket.current?.readyState !== WebSocket.OPEN) return
    pending.current.clear(); setInput(''); setInbox(null); setTrace(null); setSourceNotice(''); setAccountName(null)
    socket.current.send(JSON.stringify({ type: 'reset' }))
  }
  function insert(text: string) { setInput(text); setChatList(false); composer.current?.focus() }
  function keypress(key: string) {
    if (key === 'VOICE') { setSheet('call'); return }
    if (key === 'BACKSPACE') setInput(old => old.slice(0, -1))
    else setInput(old => old + key)
  }
  function submit(e: FormEvent) { e.preventDefault(); send() }
  const verified = stage === 'verified' || stage === 'choose_order'
  const canSend = !busy && connection === 'connected'
  const statusText = typing ? 'typing…' : connection === 'connected' ? 'online' : 'connecting…'
  const lastMessage = messages[messages.length - 1]
  const info = (title: string, children: ReactNode) => <div className="wa-sheet-content"><h3>{title}</h3>{children}<button className="wa-sheet-cancel" onClick={() => setSheet(null)}>Done</button></div>

  return <div className="wa-page">
    <header className="wa-studio-header"><a href="/" className="wa-studio-brand"><span>t.</span>Threadline<span className="wa-brand-divider" /> <small>CUSTOMER EXPERIENCE</small></a><a className="wa-studio-link" href="/" target="_blank" rel="noreferrer">Open order studio <ArrowRight size={14} /></a></header>
    <main className="wa-showcase">
      <aside className="wa-demo-panel"><div className="wa-demo-eyebrow"><MessageCircle size={16} /> THE WHATSAPP EXPERIENCE</div><h1>Your store.<br /><em>One message away.</em></h1><p className="wa-demo-lede">The conversation your customers already know.<br />Connected to the facts behind their order.</p>
        <div className="wa-connection"><span className={connection === 'connected' ? 'wa-connected-dot' : 'wa-connecting-dot'} /><strong>{connection === 'connected' ? 'WebSocket connected' : 'Reconnecting to the store…'}</strong><span>LIVE</span></div>
        <div className="wa-journey" aria-label="Customer lookup progress">{[{ name: 'Find account', active: stage === 'contact', done: stage !== 'contact' }, { name: 'Verify', active: stage === 'code', done: verified }, { name: 'Read order', active: stage === 'choose_order', done: !!trace }].map((step, i) => <div key={step.name} className={(step.active ? 'is-current ' : '') + (step.done ? 'is-done' : '')}><span>{step.done ? <Check size={12} /> : i + 1}</span>{step.name}</div>)}</div>
        <section className="wa-demo-identities"><div className="wa-panel-label">TRY A DEMO CUSTOMER <span>FICTIONAL</span></div><p>Start with “Where's my order?” Then share:</p><button onClick={() => insert('alex@example.com')} disabled={busy}><Mail size={15} /><span>alex@example.com</span><Copy size={13} /></button><button onClick={() => insert('+1 202 555 0147')} disabled={busy}><Phone size={15} /><span>+1 202 555 0147</span><Copy size={13} /></button><button className="wa-other-account" onClick={() => setShowSecond(!showSecond)}>{showSecond ? 'Hide second account' : 'Try a different customer'}<ChevronDown size={13} /></button>{showSecond && <button onClick={() => insert('casey@example.com')} disabled={busy}><Mail size={15} /><span>casey@example.com</span><Copy size={13} /></button>}</section>
        {stage === 'code' && <section className="wa-demo-inbox" aria-live="polite"><div className="wa-panel-label"><ShieldCheck size={14} /> DEMO VERIFICATION INBOX</div>{inbox?.code ? <><p>Your code for {inbox.recipient}</p><div className="wa-verification-code">{inbox.code.split('').map((number, i) => <span key={i}>{number}</span>)}</div><button disabled={busy} onClick={() => send(inbox.code!)}>Enter code in chat <ArrowRight size={14} /></button></> : <p>Use one of the fictional contacts above to receive a demo code.</p>}<small>Local simulation. No email or SMS is sent.</small></section>}
        {verified && <div className="wa-verified-note"><ShieldCheck size={18} /><span><strong>{accountName || 'Customer'} verified</strong>{orderId ? `Order #${orderId} is selected` : 'Only this customer’s orders can be accessed'}</span></div>}
        {sourceNotice && <div className="wa-source-notice" role="status"><Database size={16} />{sourceNotice}</div>}
        <div className="wa-model-state"><span className={health?.ready ? 'wa-connected-dot' : 'wa-connecting-dot'} /><span>{health?.ready ? 'Qwen3-8B · local Ollama' : 'Model is not connected'}</span><label><span className="sr-only">WhatsApp processing mode</span><select value={mode} onChange={e => setMode(e.target.value as 'model' | 'baseline')} disabled={busy}><option value="model">AI mode</option><option value="baseline">Rules baseline</option></select></label></div>
        {trace && <details className="wa-runtime-details"><summary>Look behind this reply <ChevronDown size={13} /></summary><div><p><strong>{trace.mode === 'model' ? 'Qwen3-8B tool call' : trace.mode === 'baseline_fallback' ? 'Rules fallback — model unavailable' : 'Rules baseline'}</strong><span>{(trace.latency_ms / 1000).toFixed(2)}s · {trace.usage.input_tokens} in / {trace.usage.output_tokens} out</span></p>{trace.steps.map((step, i) => <div className="wa-runtime-step" key={i}><span>{step.state === 'passed' ? <Check size={12} /> : '!'}</span><p>{step.name}<small>{step.detail}</small></p></div>)}{trace.note && <p className="wa-trace-note">{trace.note}</p>}</div></details>}
        <div className="wa-demo-controls"><button onClick={newConversation} disabled={busy || connection !== 'connected'}><RefreshCw size={14} />New conversation</button><button onClick={() => setKeyboard(!keyboard)} aria-pressed={keyboard}><Keyboard size={15} />Keyboard</button><button onClick={() => setDark(!dark)} aria-label={dark ? 'Use light WhatsApp theme' : 'Use dark WhatsApp theme'}>{dark ? <Sun size={15} /> : <Moon size={15} />}</button></div>
        <p className="wa-demo-disclosure">Classroom prototype · synthetic customer data.<br />WhatsApp-style UI; no connection to Meta or WhatsApp.</p>
      </aside>

      <section className="wa-device-stage" ref={deviceStage} aria-label="Interactive iPhone WhatsApp mockup"><div className="wa-phone-bounds" style={{ width: 417 * phoneScale, height: 876 * phoneScale }}><div className={'wa-iphone ' + (dark ? 'wa-dark' : '')} style={{ transform: `scale(${phoneScale})` }}>
        <span className="wa-hardware-button wa-mute" /><span className="wa-hardware-button wa-volume-up" /><span className="wa-hardware-button wa-volume-down" /><span className="wa-hardware-button wa-power" />
        <div className="wa-screen"><div className="wa-island"><span /></div><div className="wa-ios-status"><span>{now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span><div><Signal size={17} fill="currentColor" strokeWidth={1.6} /><Wifi size={17} strokeWidth={2.4} /><span className="wa-ios-battery"><BatteryFull size={28} strokeWidth={1.4} /><small>85</small></span></div></div>
          {chatList ? <div className="wa-chats-list"><div className="wa-chats-list-top"><button aria-label="Chat list options" onClick={() => setSheet('contact')}>•••</button><button aria-label="Open store conversation" onClick={() => setChatList(false)}><Plus size={24} /></button></div><h2>Chats</h2><div className="wa-chats-search">Ask Meta AI or Search</div><div className="wa-chats-filters"><span>All</span><span>Unread</span><span>Favourites</span><span>Groups</span></div><button className="wa-thread-row" onClick={() => setChatList(false)}><span className="wa-store-avatar">t.</span><div><strong>Threadline <small>{lastMessage ? formatTime(lastMessage.at) : formatTime(now.toISOString())}</small></strong><p>{lastMessage?.text.replaceAll('*', '').slice(0, 70) || 'Message the store'}</p></div></button><div className="wa-chats-bottom">Your order conversation stays in this local demo.</div><div className="wa-tabbar">{['Updates', 'Calls', 'Communities', 'Chats', 'Settings'].map(name => <button key={name} className={name === 'Chats' ? 'active' : ''} onClick={() => name === 'Chats' ? setChatList(false) : setSheet('call')}>{name === 'Chats' ? <MessageCircle size={23} fill="currentColor" /> : name === 'Calls' ? <Phone size={23} /> : name === 'Updates' ? <Clock3 size={23} /> : name === 'Communities' ? <BadgeCheck size={23} /> : <Smartphone size={23} />}<span>{name}</span></button>)}</div></div> : <>
          <div className="wa-chat-top"><button className="wa-back" aria-label="Back to WhatsApp chats" onClick={() => { setChatList(true); setKeyboard(false) }}><ChevronLeft size={25} strokeWidth={2.1} /></button><button className="wa-contact" onClick={() => setSheet('contact')} aria-label="View Threadline business information"><span className="wa-store-avatar">t.</span><span><strong>Threadline</strong><small>{statusText}</small></span></button><div className="wa-call-buttons"><button aria-label="Video call store" onClick={() => setSheet('call')}><Video size={22} strokeWidth={1.7} /></button><button aria-label="Call store" onClick={() => setSheet('call')}><Phone size={20} strokeWidth={1.7} /></button></div></div>
          <div className="wa-conversation" ref={scroll} role="log" aria-live="polite" aria-label="WhatsApp conversation with Threadline"><div className="wa-day-label">Today</div><div className="wa-chat-notice"><ShieldCheck size={12} /><span>You're chatting with Threadline's automated assistant. A person can help when you need one.</span></div>{messages.map((message, i) => <Bubble key={message.id} message={message} grouped={i > 0 && messages[i - 1].role === message.role} onAction={send} disabled={!canSend} />)}{typing && <div className="wa-message-row wa-in"><div className="wa-bubble wa-typing" role="status" aria-label="Threadline is typing"><span /><span /><span /></div></div>}{error && <div className="wa-channel-error" role="alert">{error}<button onClick={() => { setError(''); reconnectRef.current() }}>Reconnect</button></div>}</div>
          <div className="wa-composer-area"><form className="wa-composer" onSubmit={submit}><button type="button" className="wa-plus" aria-label="Attachments and chat actions" onClick={() => setSheet('attachments')}><Plus size={28} strokeWidth={1.5} /></button><div className="wa-text-input"><label className="sr-only" htmlFor="wa-message-input">Message Threadline</label><textarea id="wa-message-input" ref={composer} rows={1} value={input} onChange={e => setInput(e.target.value)} maxLength={2000} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} placeholder="Message" disabled={!canSend} /><button type="button" aria-label="Stickers and emoji" onClick={() => setInput(old => old + '😊')}><Sticker size={22} strokeWidth={1.5} /></button>{!input && <button type="button" aria-label="Camera attachment information" onClick={() => setSheet('attachments')}><Camera size={22} strokeWidth={1.5} /></button>}</div>{input.trim() ? <button className="wa-send" type="submit" aria-label="Send WhatsApp message" disabled={!canSend}><Send size={22} fill="currentColor" strokeWidth={1.3} /></button> : <button className="wa-mic" type="button" aria-label="Voice messaging information" onClick={() => setSheet('call')}><Mic size={24} strokeWidth={1.6} /></button>}</form>{keyboard && <IOSKeyboard onKey={keypress} onClose={() => setKeyboard(false)} onSend={() => send()} />}</div>
          </>}
          <div className="wa-home-indicator" />
          {sheet && <div className="wa-sheet-backdrop" onClick={() => setSheet(null)}><div className="wa-sheet" role="dialog" aria-modal="true" aria-label={sheet === 'contact' ? 'Threadline contact information' : sheet === 'attachments' ? 'Chat actions' : 'Messaging demo information'} onClick={e => e.stopPropagation()}><div className="wa-sheet-handle" /><button className="wa-sheet-close" aria-label="Close information" onClick={() => setSheet(null)} autoFocus><X size={18} /></button>{sheet === 'contact' ? info('Threadline', <><span className="wa-store-avatar wa-contact-large">t.</span><p>Clothes for everyday.<br />Care that carries on after checkout.</p><div className="wa-business-info"><span>Retail & apparel</span><span>Automated order & returns support</span><span>Local classroom business profile</span></div></>) : sheet === 'attachments' ? info('How can we help?', <div className="wa-attachment-actions"><button onClick={() => send('Where is my order?')} disabled={!canSend}><Database size={24} /><span>Track order</span></button><button onClick={() => send('Can I return an item?')} disabled={!canSend}><RefreshCw size={24} /><span>Check return</span></button><button onClick={() => send('I want to speak to a person.')} disabled={!canSend}><MessageCircle size={24} /><span>Talk to support</span></button></div>) : info('A messaging-first demo', <p>Text messages are connected to our AI and live synthetic order system. Calls, photos, and audio aren't connected in this classroom prototype.</p>)}</div></div>}
        </div>
      </div></div><div className="wa-device-caption"><Smartphone size={12} /><span>iPhone · 393 × 852</span><span>Interactive prototype</span></div></section>
    </main>
  </div>
}
