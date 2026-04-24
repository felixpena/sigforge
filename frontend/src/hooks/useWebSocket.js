import { useEffect, useRef, useCallback, useState } from 'react'

function getWsUrl() {
  if (import.meta.env.VITE_WS_URL) {
    return import.meta.env.VITE_WS_URL + '/ws'
  }
  // Derive from current page host so it works in Docker and any deployment
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = import.meta.env.VITE_API_URL
    ? import.meta.env.VITE_API_URL.replace(/^https?:/, protocol)
    : `${protocol}//${window.location.hostname}:8000`
  return host + '/ws'
}

const WS_URL = getWsUrl()

// Reconnect immediately on first disconnect, then back off up to 5s max
const INITIAL_DELAY = 0
const BASE_DELAY = 500
const MAX_DELAY = 5000

export function useWebSocket(onMessage) {
  const ws = useRef(null)
  const reconnectTimeout = useRef(null)
  const attemptRef = useRef(0)
  const onMessageRef = useRef(onMessage)
  const unmountedRef = useRef(false)
  const [connected, setConnected] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)

  onMessageRef.current = onMessage

  const getDelay = (attempt) => {
    if (attempt === 0) return INITIAL_DELAY
    // Exponential backoff: 500ms, 1s, 2s, 4s, 5s (capped)
    return Math.min(BASE_DELAY * Math.pow(2, attempt - 1), MAX_DELAY)
  }

  const connect = useCallback(() => {
    if (unmountedRef.current) return
    if (ws.current?.readyState === WebSocket.CONNECTING) return
    if (ws.current?.readyState === WebSocket.OPEN) return

    try {
      const socket = new WebSocket(WS_URL)

      socket.onopen = () => {
        if (unmountedRef.current) { socket.close(); return }
        attemptRef.current = 0
        setConnected(true)
        setReconnecting(false)

        // Keepalive ping every 20s
        const pingInterval = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send('ping')
          } else {
            clearInterval(pingInterval)
          }
        }, 20000)
        socket._pingInterval = pingInterval
      }

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          onMessageRef.current?.(data)
        } catch (_) {
          // pong or non-JSON — ignore
        }
      }

      socket.onclose = () => {
        if (socket._pingInterval) clearInterval(socket._pingInterval)
        if (unmountedRef.current) return
        setConnected(false)
        scheduleReconnect()
      }

      socket.onerror = () => {
        // onclose fires immediately after onerror — let it handle reconnect
        socket.close()
      }

      ws.current = socket
    } catch (_) {
      scheduleReconnect()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const scheduleReconnect = useCallback(() => {
    if (unmountedRef.current) return
    if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current)

    const attempt = attemptRef.current
    const delay = getDelay(attempt)
    attemptRef.current = attempt + 1
    setReconnecting(true)

    reconnectTimeout.current = setTimeout(() => {
      if (!unmountedRef.current) connect()
    }, delay)
  }, [connect]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    unmountedRef.current = false
    connect()
    return () => {
      unmountedRef.current = true
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current)
      if (ws.current) {
        ws.current.onclose = null // suppress reconnect on intentional unmount
        ws.current.close()
      }
    }
  }, [connect])

  return { connected, reconnecting }
}
