import React from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource/dm-sans/400.css'
import '@fontsource/dm-sans/500.css'
import '@fontsource/dm-sans/600.css'
import '@fontsource/cormorant-garamond/400.css'
import '@fontsource/cormorant-garamond/500.css'
import '@fontsource/cormorant-garamond/400-italic.css'
import App from './App'
import WhatsAppDemo from './WhatsApp'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode>{location.pathname.startsWith('/whatsapp') ? <WhatsAppDemo /> : <App />}</React.StrictMode>)
