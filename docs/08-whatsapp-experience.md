# 08 · WhatsApp customer experience — v0.3

The customer experience now lives in a **separate tab at `/whatsapp`**. The existing studio remains the order system, agent inbox, and evaluator view. The phone is a functional React interface, not a picture or a fake conversation generator.

## The service idea

A customer messages the store in a familiar chat. They should not have to know an internal customer ID or search for an order number before asking for help.

1. **Ask naturally.** “Hi, where is my order?”
2. **Find the account.** The assistant asks for the checkout email or phone. The backend normalizes and matches it against the customer table.
3. **Verify access.** A short-lived six-digit challenge confirms the demo identity. Codes appear only in the local evaluator inbox outside the phone; no real SMS or email is sent.
4. **Resolve the purchase.** One matching order can be selected automatically. Multiple relevant orders produce native-style reply choices, so the service asks instead of guessing.
5. **Read and respond.** Qwen3-8B selects an allowed support tool. The backend reads the current order and renders the reply from verified facts. A return question can resolve a named item such as the Oxford.
6. **Continue or hand off.** The conversation retains the selected order. Exceptions create a ticket with the context attached.

Email or a typed phone number is a lookup key, not proof of ownership. The code delivery and verification controls are explicitly simulated; production must use the retailer's actual authenticated contact/identity flow.

## Try it

Open the WhatsApp demo from the studio header or visit **http://127.0.0.1:5173/whatsapp**.

| Demo customer | Checkout email | Checkout phone | Orders |
| --- | --- | --- | --- |
| Alex | `alex@example.com` | `+1 202 555 0147` | 4812–4816; initially two active orders |
| Casey | `casey@example.com` | `+1 202 555 0186` | 4901 |

Start with “Where is my order?”, provide a contact, and enter the code from the demo inbox. For Alex, choose #4812. The reply includes available item/variant, carrier, estimate, synthetic tracking reference, purchase date, total, and destination city. These are all database fields, not model inventions.

To prove the integration, keep the phone tab open and change #4812 in the order studio. The phone receives a source-change event. Ask “Can you check again?” to perform a new authorized read. The notice itself does not present an unrequested or unverified new status.

## Architecture

```mermaid
flowchart LR
    PHONE[iPhone-style WhatsApp UI] <-->|WebSocket messages, receipts, typing and reconnect| CHANNEL[Channel adapter]
    CHANNEL <--> SESSION[(Persistent channel session)]
    CHANNEL --> ID[Email / phone lookup + demo code verification]
    ID --> CUSTOMER[(Customer table)]
    CHANNEL --> FLOW[Existing bounded support workflow]
    FLOW <--> MODEL[Qwen3-8B / Ollama]
    FLOW --> TOOLS[Authorized order and return tools]
    TOOLS --> DB[(Live synthetic order database)]
    TOOLS --> HUMAN[Agent inbox]
    CONSOLE[Separate order studio] --> DB
    CONSOLE -->|Scoped source-change event| CHANNEL
```

The browser connects to `/api/whatsapp/ws`. The Vite proxy forwards WebSocket upgrades to FastAPI. Session capabilities are sent in the opening frame rather than URL query parameters. Customer messages carry stable request IDs; handled replays restore the conversation instead of repeating inference or creating another ticket. In-process connection maps support the local single-worker demo.

The transport supplies genuine acknowledgements and processing events. The tick marks represent delivery to and reading by this demo service; they are not WhatsApp network receipts. Typing indicates a real request being processed, not artificial token streaming. Reconnect uses backoff and a persisted session. Codes expire after five minutes and allow five attempts; identifiers and verification codes are not forwarded to model history.

The evaluator inbox is gated by the same local demo console capability as the studio. It deliberately simulates delivery, and should not be reused as a production authentication system. No customer details are returned through the public channel before verification. Source-change notifications are scoped to the verified owner.

## Visual direction and references

The selected direction follows the light iPhone conversation view, using a **393 × 852 logical screen** inside a proportioned device frame. The design includes a Dynamic Island, status bar, translucent circular controls, contact avatar, white incoming and green outgoing messages, tails, timestamps, read ticks, native-style business replies, composer, and home indicator. Dark mode and an optional working iOS-style keyboard support demonstrations. The wallpaper is an original local vector illustration.

Multiple iOS references were compared; older screenshots were used to understand persistent chat conventions, while the newer chat-screen reference informed the translucent controls. WhatsApp releases and account rollouts have visual variations, so this is a recreation of the chosen reference style, not a claim that every installed version is identical.

| Reference | Design evidence reviewed |
| --- | --- |
| [WABetaInfo: chat-screen rollout, June 2026](https://wabetainfo.com/whatsapp-is-rolling-out-liquid-glass-for-the-chat-interface-on-ios/) | Light and dark conversation screens; floating composer and header controls |
| [WABetaInfo: chat-screen preview, May 2026](https://wabetainfo.com/whatsapp-to-test-liquid-glass-design-for-the-chat-interface/) | Header, composer, and layering details |
| [Meta: keeping WhatsApp fresh and approachable](https://www.meta.com/design-at-meta/blog/whatsapp-user-interface-update/) | Official device-native design direction |
| [Trovaprezzi: iOS chat-interface comparison](https://www.trovaprezzi.it/magazine/tech/whatsapp-il-liquid-glass-sempre-piu-presente-nellinterfaccia-delle-chat) | Collage of chat and control treatments |
| [NuvemMag: iOS design screenshots](https://nuvemmag.com/whatsapp-iosta-liquid-glass-tasarimini-bazi-kullanicilarla-test-ediyor/) | Relative spacing, handset framing, and conversation chrome |
| [teltarif: iPhone interface comparison](https://www.teltarif.de/en/whatsapp-liquid-glass-design-update/news/103012.html) | Light/dark appearance and device context |
| [Candid Technology: iOS refreshed interface](https://candid.technology/whatsappchat-filtering-revamped-interface-passkeys-update/) | Chat-list hierarchy and filtering conventions |
| [TechTarget: illustrated WhatsApp conversation](https://www.techtarget.com/searchmobilecomputing/definition/WhatsApp) | Established message alignment and metadata conventions |

The downloaded research images remain in ignored local QA files; the application uses its own markup, icons, and wallpaper. Calling, camera uploads, and audio recording display an honest information sheet rather than pretending those services are connected.

## Verification and limits

The current suite has **46 passing backend tests**, including 17 channel-specific checks for account matching, verification boundaries, expiry, attempt limits, preserved intent, code/contact exclusion from model history, order ownership, request deduplication, persistence, scoped notifications, and WebSocket protocol validation.

Browser checks used genuine Qwen inference for the complete contact → verification → order selection → rich reply journey. A second studio tab changed a saved record; the phone received a WebSocket event and its next reply reflected the new source value. Reload restored the conversation. Light/dark themes, keyboard, chat-list navigation, and responsive layouts were inspected.

This remains a local synthetic prototype. A real WhatsApp Business integration would use Meta's messaging APIs and incoming webhooks in a channel adapter, with the same support workflow underneath. It would not replace the native WhatsApp client with this browser mockup. See the [official developer hub](https://whatsappbusiness.com/developers/developer-hub/) and [Meta-hosted receiving-messages documentation](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/receivingMessages/) for that integration pattern; no Meta account, production credential, email/SMS service, or retailer ERP is connected here.
