import { useEffect, useRef, useCallback, useState } from 'react'

const WS_URL = (import.meta.env.VITE_WS_URL || 'ws://localhost:8000') + '/ws'
const RECONNECT_DELAY = 3000
const MAX_RECONNECT_DELAY = 30000

export function useWebSocket(onMessage) {
  const ws = useRef(null)
  const reconnectTimeout = useRef(null)
  const reconnectDelay = useRef(RECONNECT_DELAY)
  const onMessageRef = useRef(onMessage)
  const [connected, setConnected] = useState(false)

  onMessageRef.current = onMessage

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return

    try {
      const socket = new WebSocket(WS_URL)

      socket.onopen = () => {
        setConnected(true)
        reconnectDelay.current = RECONNECT_DELAY
        // Send ping every 20s to keep alive
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
        } catch (e) {
          // pong or non-JSON
        }
      }

      socket.onclose = () => {
        setConnected(false)
        if (socket._pingInterval) clearInterval(socket._pingInterval)
        scheduleReconnect()
      }

      socket.onerror = () => {
        socket.close()
      }

      ws.current = socket
    } catch (e) {
      scheduleReconnect()
    }
  }, [])

  const scheduleReconnect = useCallback(() => {
    if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current)
    reconnectTimeout.current = setTimeout(() => {
      reconnectDelay.current = Math.min(reconnectDelay.current * 1.5, MAX_RECONNECT_DELAY)
      connect()
    }, reconnectDelay.current)
  }, [connect])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current)
      if (ws.current) {
        ws.current.onclose = null // prevent reconnect on unmount
        ws.current.close()
      }
    }
  }, [connect])

  return { connected }
}
