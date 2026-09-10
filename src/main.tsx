import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { CharterProvider } from './store/charterStore.tsx'
import { ThemeProvider } from './store/themeStore.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <CharterProvider>
        <App />
      </CharterProvider>
    </ThemeProvider>
  </StrictMode>,
)
