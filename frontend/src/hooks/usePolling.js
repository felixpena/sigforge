import { useEffect, useRef, useState } from 'react'

function getApiBase() {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL
  return `${window.location.protocol}//${window.location.hostname}:8000`
}

const POLL_INTERVAL = 5000

export function usePolling(onMessage) {
  const [connected, setConnected] = useState(false)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  useEffect(() => {
    const base = getApiBase()
    let cancelled = false

    async function poll() {
      const timestamp = new Date().toISOString()
      const emit = (type, payload) => onMessageRef.current?.({ type, payload, timestamp })

      const [portfolio, trades, signals, status, positions, log, pnlHistory, lastScan] =
        await Promise.allSettled([
          fetch(`${base}/api/portfolio`).then(r => r.json()),
          fetch(`${base}/api/trades`).then(r => r.json()),
          fetch(`${base}/api/signals`).then(r => r.json()),
          fetch(`${base}/health`).then(r => r.json()),
          fetch(`${base}/api/positions`).then(r => r.json()),
          fetch(`${base}/api/log`).then(r => r.json()),
          fetch(`${base}/api/pnl-history`).then(r => r.json()),
          fetch(`${base}/api/last-scan`).then(r => r.json()),
        ])

      if (cancelled) return

      const anyOk = [portfolio, trades, signals, status, positions, log, pnlHistory, lastScan]
        .some(r => r.status === 'fulfilled')
      setConnected(anyOk)

      if (portfolio.status === 'fulfilled') emit('portfolio', portfolio.value)
      if (trades.status === 'fulfilled')    emit('trade_history', trades.value)
      if (status.status === 'fulfilled')    emit('system_status', status.value)
      if (positions.status === 'fulfilled') emit('positions', positions.value)
      if (log.status === 'fulfilled')       emit('log_history', log.value)
      if (pnlHistory.status === 'fulfilled') emit('pnl_history', pnlHistory.value)
      if (lastScan.status === 'fulfilled' && lastScan.value?.scan_timestamp) {
        emit('scan_complete', lastScan.value)
      }
    }

    poll()
    const id = setInterval(poll, POLL_INTERVAL)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return { connected, reconnecting: false }
}
