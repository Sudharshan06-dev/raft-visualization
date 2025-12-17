import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';

const nodeCoords = {
  A: { x: 80, y: 100 },
  B: { x: 280, y: 100 },
  C: { x: 180, y: 240 },
};

const RaftVisualizationWithWebSocket = () => {
  const [inputKey, setInputKey] = useState('');
  const [inputField, setInputField] = useState('');
  const [inputValue, setInputValue] = useState('');

  // Logs per node, driven entirely by backend
  const [nodeLogEntries, setNodeLogEntries] = useState({
    A: [],
    B: [],
    C: [],
  });

  // KV store with key -> field -> value structure
  // Structure: { key1: { field1: value1, field2: value2 }, key2: { fieldA: valueA } }
  const [kvMetadata, setKvMetadata] = useState({});
  const [committedKVStore, setCommittedKVStore] = useState({});

  const [activeMessage, setActiveMessage] = useState(null);
  const [leaderId, setLeaderId] = useState(null);
  const [currentTerm, setCurrentTerm] = useState(null);
  const [lastLogIndex, setLastLogIndex] = useState(null);
  const [lastLogTerm, setLastLogTerm] = useState(null);
  const [followers, setFollowers] = useState([]);
  const [peerResponses, setPeerResponses] = useState({});
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [lastHeartbeatTime, setLastHeartbeatTime] = useState(null);
  const [debugMessages, setDebugMessages] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const wsRef = useRef(null);

  const addDebug = (msg) => {
    console.log(`[DEBUG] ${msg}`);
    setDebugMessages((prev) => [...prev.slice(-4), msg]);
  };

  // WebSocket setup
  useEffect(() => {
    const connectWebSocket = () => {
      try {
        addDebug('Attempting WebSocket connection to ws://localhost:8765/ws');
        const wsUrl = 'ws://localhost:8765/ws';
        wsRef.current = new WebSocket(wsUrl);

        wsRef.current.onopen = () => {
          addDebug('✅ WebSocket CONNECTED');
          setConnectionStatus('connected');
        };

        wsRef.current.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            addDebug(`📨 Message received: ${message.type}`);
            handleWebSocketMessage(message);
          } catch (e) {
            addDebug(`❌ Parse error: ${e.message}`);
          }
        };

        wsRef.current.onerror = (error) => {
          addDebug(`❌ WebSocket ERROR: ${error.message || error.toString()}`);
          setConnectionStatus('error');
        };

        wsRef.current.onclose = () => {
          addDebug('⚠️ WebSocket DISCONNECTED - Reconnecting in 3s');
          setConnectionStatus('disconnected');
          setTimeout(connectWebSocket, 3000);
        };
      } catch (e) {
        addDebug(`❌ Connection failed: ${e.message}`);
        setConnectionStatus('error');
        setTimeout(connectWebSocket, 3000);
      }
    };

    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const handleWebSocketMessage = (message) => {
    try {
      switch (message.type) {
        case 'heartbeat':
          handleHeartbeat(message);
          break;
        case 'peer_response':
          handlePeerResponse(message);
          break;
        case 'node_state_change':
          handleNodeStateChange(message);
          break;
        case 'log_entry':
          handleLogEntry(message);
          break;
        case 'entries_committed':
          handleEntriesCommitted(message);
          break;
        case 'kv_store_update':
          handleKVStoreUpdate(message);
          break;
        default:
          addDebug(`⚠️ Unknown message type: ${message.type}`);
      }
    } catch (e) {
      addDebug(`❌ Handler error: ${e.message}`);
    }
  };

  const handleHeartbeat = (message) => {
    const {
      leader_id,
      current_term,
      last_log_index,
      last_log_term,
      followers: hbFollowers,
      timestamp,
    } = message;

    setLeaderId(leader_id || null);
    setCurrentTerm(current_term ?? null);
    setLastLogIndex(last_log_index ?? null);
    setLastLogTerm(last_log_term ?? null);
    setFollowers(Array.isArray(hbFollowers) ? hbFollowers : []);
    setLastHeartbeatTime(timestamp ? new Date(timestamp) : new Date());

    // Reset peer responses for this heartbeat
    const newResponses = {};
    (hbFollowers || []).forEach((f) => {
      newResponses[f] = { success: null, term: null, matchIndex: null };
    });
    setPeerResponses(newResponses);

    if (leader_id) {
      setActiveMessage({ type: 'heartbeat', leader_id });
      setTimeout(() => setActiveMessage(null), 1500);
    }
  };

  const handlePeerResponse = (message) => {
    const { peer_id, leader_id, result } = message;
    if (!peer_id || !leader_id || !result) {
      addDebug('peer_response missing fields');
      return;
    }

    setPeerResponses((prev) => ({
      ...prev,
      [peer_id]: {
        success: !!result.success,
        term: result.term ?? null,
        matchIndex: result.matchIndex ?? null,
      },
    }));

    if (result.success) {
      setActiveMessage({
        type: 'peer_response',
        from: peer_id,
        to: leader_id,
      });
      setTimeout(() => setActiveMessage(null), 1500);
    }
  };

  const handleNodeStateChange = (message) => {
    const { node_id, new_state, current_term } = message;
    if (new_state === 'leader') {
      setLeaderId(node_id);
      if (current_term != null) setCurrentTerm(current_term);
    }
  };

  const handleLogEntry = (message) => {
    const { node_id, log_entry, log_index, committed } = message;
    if (!node_id || !log_entry || log_index == null) {
      addDebug('⚠️ log_entry missing fields');
      return;
    }

    addDebug(`Log entry on Node ${node_id}: "${log_entry}"`);

    setNodeLogEntries((prev) => ({
      ...prev,
      [node_id]: [
        ...prev[node_id],
        {
          id: log_index,
          value: log_entry.command || String(log_entry),
          committed: !!committed,
        },
      ],

    }));
  };

  // React component - Replace handleEntriesCommitted function

  const handleEntriesCommitted = (message) => {
    try {
      const { committed_until_index } = message;
      addDebug(`Entries committed up to index ${committed_until_index}`);

      // UPDATE existing entries (don't create duplicates!)
      setNodeLogEntries((prev) => {
        const updated = {};

        ['A', 'B', 'C'].forEach((nId) => {
          updated[nId] = prev[nId].map((entry) => {
            // Only update entries that exist and aren't already committed
            if (entry.id <= committed_until_index && !entry.committed) {
              return { ...entry, committed: true };
            }
            return entry;
          });
        });

        return updated;
      });
    } catch (e) {
      addDebug(` Error in handleEntriesCommitted: ${e.message}`);
    }
  };

  const handleKVStoreUpdate = (message) => {
    try {
      const { node_id, log_index, key, field, value, timestamp } = message;

      // Validate all required fields
      if (!node_id || log_index == null) {
        addDebug(`KV update missing: node_id=${node_id}, log_index=${log_index}`);
        return;
      }

      if (!key || !field || value === undefined || value === null) {
        addDebug(`KV update invalid: key=${key}, field=${field}, value=${value}`);
        return;
      }

      // Create unique ID
      const updateId = `${node_id}-${log_index}-${key}-${field}`;

      // Optional: Track processed updates
      setKvMetadata((prev) => ({
        ...prev,
        [`${key}-${field}`]: {
          node_id,
          log_index,
          timestamp: timestamp || new Date().toISOString(),
          updated_at: new Date().toLocaleTimeString(),
        },
      }));

      addDebug(`KV Store [Node ${node_id}]: ${key}.${field} = ${value}`);

      // Update main data
      setCommittedKVStore((prev) => {
        const existing = prev[String(key)]?.[String(field)];

        if (existing === String(value)) {
          return prev;
        }

        return {
          ...prev,
          [String(key)]: {
            ...(prev[String(key)] || {}),
            [String(field)]: String(value),
          },
        };
      });
    } catch (e) {
      addDebug(`KV store update error: ${e.message}`);
    }
  };

  const handleSubmitKVEntry = async () => {
    if (!inputKey.trim() || !inputField.trim() || !inputValue.trim()) {
      alert('Please enter key, field, and value');
      return;
    }

    setIsSubmitting(true);

    const payload = {
      type: 'client_command',
      command: `SET ${inputKey}.${inputField} = ${inputValue}`,
      key: inputKey,
      field: inputField,
      value: inputValue,
    };

    try {
      const response = await fetch(`http://localhost:8765/kv-store`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (!response.ok) {
        console.error('SET failed:', data);
        throw new Error(data.message || `HTTP ${response.status}`);
      }

      console.log('SET successful:', data);

      // Clear inputs on success
      setInputKey('');
      setInputField('');
      setInputValue('');
      return data;
    } catch (err) {
      console.error('SET error:', err);
      throw err;
    } finally {
      setIsSubmitting(false);
    }
  };


  const nodeColors = {
    leader: {
      gradient: 'linear-gradient(135deg, #f97316 0%, #ef4444 100%)',
      shadow: 'rgba(249, 115, 22, 0.5)',
    },
    follower: {
      gradient: 'linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%)',
      shadow: 'rgba(59, 130, 246, 0.5)',
    },
  };

  const getNodeState = (nodeId) => {
    if (!leaderId) return 'FOLLOWER';
    return nodeId === leaderId ? 'LEADER' : 'FOLLOWER';
  };

  // Enhanced: Get rows with metadata
  const getKVStoreRows = () => {
    const rows = [];
    Object.entries(committedKVStore).forEach(([key, fieldsObj]) => {
      if (fieldsObj && typeof fieldsObj === 'object') {
        Object.entries(fieldsObj).forEach(([field, value]) => {
          const metaKey = `${key}-${field}`;
          rows.push({
            key,
            field,
            value,
            node_id: kvMetadata[metaKey]?.node_id || '-',
            updated_at: kvMetadata[metaKey]?.updated_at || '-',
          });
        });
      }
    });
    return rows;
  };

  
// Enhanced table with node and timestamp columns
const enhancedTableUI = (
  <div
    style={{
      background: 'rgba(30, 41, 59, 0.8)',
      border: '1px solid rgba(71, 85, 105, 0.4)',
      borderRadius: '12px',
      padding: '1.5rem',
      backdropFilter: 'blur(10px)',
      marginBottom: '2rem',
    }}
  >
    <h2
      style={{
        fontSize: '1.2rem',
        fontWeight: '700',
        margin: '0 0 1rem 0',
        color: '#10b981',
      }}
    >
      Committed KV Store (State Machine)
    </h2>
    {getKVStoreRows().length === 0 ? (
      <div
        style={{
          color: '#64748b',
          fontSize: '12px',
          fontStyle: 'italic',
          padding: '1rem',
        }}
      >
        No committed entries yet...
      </div>
    ) : (
      <div style={{ overflowX: 'auto' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '12px',
          }}
        >
          <thead>
            <tr
              style={{
                borderBottom: '2px solid rgba(16, 185, 129, 0.3)',
              }}
            >
              <th
                style={{
                  padding: '0.75rem',
                  textAlign: 'left',
                  color: '#10b981',
                  fontWeight: '700',
                  width: '20%',
                }}
              >
                Key
              </th>
              <th
                style={{
                  padding: '0.75rem',
                  textAlign: 'left',
                  color: '#10b981',
                  fontWeight: '700',
                  width: '20%',
                }}
              >
                Field
              </th>
              <th
                style={{
                  padding: '0.75rem',
                  textAlign: 'left',
                  color: '#10b981',
                  fontWeight: '700',
                  width: '30%',
                }}
              >
                Value
              </th>
              <th
                style={{
                  padding: '0.75rem',
                  textAlign: 'left',
                  color: '#10b981',
                  fontWeight: '700',
                  width: '15%',
                }}
              >
                Updated
              </th>
            </tr>
          </thead>
          <tbody>
            {getKVStoreRows().map((row, idx) => (
              <motion.tr
                key={`kv-${row.key}-${row.field}-${idx}`}
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                style={{
                  borderBottom: '1px solid rgba(71, 85, 105, 0.3)',
                }}
              >
                <td
                  style={{
                    padding: '0.75rem',
                    color: '#cbd5e1',
                    fontFamily: 'monospace',
                    wordBreak: 'break-word',
                  }}
                >
                  {String(row.key)}
                </td>
                <td
                  style={{
                    padding: '0.75rem',
                    color: '#cbd5e1',
                    fontFamily: 'monospace',
                    wordBreak: 'break-word',
                  }}
                >
                  {String(row.field)}
                </td>
                <td
                  style={{
                    padding: '0.75rem',
                    color: '#10b981',
                    fontFamily: 'monospace',
                    wordBreak: 'break-word',
                  }}
                >
                  {String(row.value)}
                </td>
                <td
                  style={{
                    padding: '0.75rem',
                    color: '#94a3b8',
                    fontSize: '11px',
                  }}
                >
                  {row.updated_at}
                </td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </div>
);

  return (
    <div
      style={{
        width: '100%',
        minHeight: '100vh',
        background:
          'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)',
        padding: '2rem',
        fontFamily: 'system-ui, Avenir, Helvetica, Arial, sans-serif',
        color: '#f1f5f9',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Debug Panel */}
      <div
        style={{
          position: 'fixed',
          top: '10px',
          right: '10px',
          background: 'rgba(15, 23, 42, 0.95)',
          border: '1px solid rgba(71, 85, 105, 0.5)',
          borderRadius: '8px',
          padding: '10px',
          maxWidth: '300px',
          fontSize: '10px',
          color: '#cbd5e1',
          zIndex: 1000,
          maxHeight: '200px',
          overflowY: 'auto',
        }}
      >
      </div>

      {/* Header */}
      <div
        style={{
          marginBottom: '2rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div>
          <h1
            style={{
              fontSize: '2.5rem',
              fontWeight: 'bold',
              margin: '0 0 0.5rem 0',
            }}
          >
            RAFT Consensus Visualization
          </h1>
          <p
            style={{
              color: '#cbd5e1',
              margin: 0,
              fontSize: '0.95rem',
            }}
          >
            Real-time distributed consensus with WebSocket heartbeats and peer
            responses
          </p>
        </div>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-end',
            gap: '0.5rem',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              fontSize: '12px',
            }}
          >
            <div
              style={{
                width: '12px',
                height: '12px',
                borderRadius: '50%',
                background:
                  connectionStatus === 'connected'
                    ? '#10b981'
                    : connectionStatus === 'error'
                      ? '#ef4444'
                      : '#f59e0b',
                animation:
                  connectionStatus === 'connected' ? 'pulse 2s infinite' : 'none',
              }}
            />
            <span>{connectionStatus.toUpperCase()}</span>
          </div>
          {lastHeartbeatTime && (
            <div style={{ fontSize: '10px', color: '#64748b' }}>
              Last heartbeat: {lastHeartbeatTime.toLocaleTimeString()}
            </div>
          )}
        </div>
      </div>

      {/* Input KV Store - Updated for Key.Field = Value */}
      <div
        style={{
          background: 'rgba(30, 41, 59, 0.8)',
          border: '1px solid rgba(71, 85, 105, 0.4)',
          borderRadius: '12px',
          padding: '1.5rem',
          marginBottom: '2rem',
          backdropFilter: 'blur(10px)',
        }}
      >
        <h2
          style={{
            fontSize: '1.2rem',
            fontWeight: '700',
            margin: '0 0 1rem 0',
            color: '#f1f5f9',
          }}
        >
          Input KV Store Entry
        </h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 1fr auto',
            gap: '1rem',
            alignItems: 'flex-end',
          }}
        >
          <div>
            <label
              style={{
                fontSize: '0.9rem',
                color: '#cbd5e1',
                display: 'block',
                marginBottom: '0.5rem',
              }}
            >
              Key
            </label>
            <input
              type="text"
              value={inputKey}
              onChange={(e) => setInputKey(e.target.value)}
              placeholder="Enter key..."
              disabled={isSubmitting || connectionStatus !== 'connected'}
              style={{
                width: '100%',
                padding: '0.75rem',
                borderRadius: '6px',
                border: '1px solid rgba(71, 85, 105, 0.5)',
                background: 'rgba(15, 23, 42, 0.6)',
                color: '#f1f5f9',
                fontFamily: 'inherit',
                fontSize: '0.95rem',
                opacity:
                  isSubmitting || connectionStatus !== 'connected' ? 0.6 : 1,
              }}
            />
          </div>
          <div>
            <label
              style={{
                fontSize: '0.9rem',
                color: '#cbd5e1',
                display: 'block',
                marginBottom: '0.5rem',
              }}
            >
              Field
            </label>
            <input
              type="text"
              value={inputField}
              onChange={(e) => setInputField(e.target.value)}
              placeholder="Enter field..."
              disabled={isSubmitting || connectionStatus !== 'connected'}
              style={{
                width: '100%',
                padding: '0.75rem',
                borderRadius: '6px',
                border: '1px solid rgba(71, 85, 105, 0.5)',
                background: 'rgba(15, 23, 42, 0.6)',
                color: '#f1f5f9',
                fontFamily: 'inherit',
                fontSize: '0.95rem',
                opacity:
                  isSubmitting || connectionStatus !== 'connected' ? 0.6 : 1,
              }}
            />
          </div>
          <div>
            <label
              style={{
                fontSize: '0.9rem',
                color: '#cbd5e1',
                display: 'block',
                marginBottom: '0.5rem',
              }}
            >
              Value
            </label>
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Enter value..."
              disabled={isSubmitting || connectionStatus !== 'connected'}
              style={{
                width: '100%',
                padding: '0.75rem',
                borderRadius: '6px',
                border: '1px solid rgba(71, 85, 105, 0.5)',
                background: 'rgba(15, 23, 42, 0.6)',
                color: '#f1f5f9',
                fontFamily: 'inherit',
                fontSize: '0.95rem',
                opacity:
                  isSubmitting || connectionStatus !== 'connected' ? 0.6 : 1,
              }}
            />
          </div>
          <button
            onClick={handleSubmitKVEntry}
            disabled={
              isSubmitting ||
              connectionStatus !== 'connected' ||
              !inputKey.trim() ||
              !inputField.trim() ||
              !inputValue.trim()
            }
            style={{
              background: isSubmitting
                ? 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)'
                : 'linear-gradient(135deg, #a855f7 0%, #ec4899 100%)',
              color: 'white',
              fontWeight: '700',
              padding: '0.75rem 1.5rem',
              border: 'none',
              borderRadius: '8px',
              cursor:
                isSubmitting || connectionStatus !== 'connected'
                  ? 'not-allowed'
                  : 'pointer',
              fontSize: '14px',
              opacity:
                isSubmitting || connectionStatus !== 'connected' ? 0.6 : 1,
              transition: 'all 0.3s ease',
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
            }}
          >
            {isSubmitting
              ? 'Processing...'
              : connectionStatus !== 'connected'
                ? 'Waiting...'
                : 'Submit'}
          </button>
        </div>
      </div>

      {/* Node Visualization + Logs */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 2fr',
          gap: '2rem',
          marginBottom: '2rem',
        }}
      >
        {/* Node Visualization */}
        <div
          style={{
            background: 'rgba(30, 41, 59, 0.8)',
            border: '1px solid rgba(71, 85, 105, 0.4)',
            borderRadius: '12px',
            padding: '2rem',
            backdropFilter: 'blur(10px)',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <h3
            style={{
              fontSize: '1.1rem',
              fontWeight: '700',
              marginTop: 0,
              marginBottom: '1.5rem',
            }}
          >
            Node Network (Term {currentTerm ?? '-'})
          </h3>

          <div
            style={{
              position: 'relative',
              flex: 1,
              minHeight: '300px',
              marginBottom: '1.5rem',
            }}
          >
            <svg
              width="100%"
              height="100%"
              viewBox="0 0 400 320"
              style={{ position: 'absolute', inset: 0 }}
            >
              {/* Static connections */}
              <line
                x1={nodeCoords.A.x}
                y1={nodeCoords.A.y}
                x2={nodeCoords.B.x}
                y2={nodeCoords.B.y}
                stroke="#475569"
                strokeWidth="1"
                strokeDasharray="3,3"
              />
              <line
                x1={nodeCoords.A.x}
                y1={nodeCoords.A.y}
                x2={nodeCoords.C.x}
                y2={nodeCoords.C.y}
                stroke="#475569"
                strokeWidth="1"
                strokeDasharray="3,3"
              />
              <line
                x1={nodeCoords.B.x}
                y1={nodeCoords.B.y}
                x2={nodeCoords.C.x}
                y2={nodeCoords.C.y}
                stroke="#475569"
                strokeWidth="1"
                strokeDasharray="3,3"
              />

              {/* Heartbeats */}
              {activeMessage?.type === 'heartbeat' &&
                leaderId &&
                followers.map((f) => (
                  <motion.line
                    key={`hb-${f}`}
                    x1={nodeCoords[leaderId].x}
                    y1={nodeCoords[leaderId].y}
                    x2={nodeCoords[f].x}
                    y2={nodeCoords[f].y}
                    stroke="#06b6d4"
                    strokeWidth="2"
                    initial={{ pathLength: 0, opacity: 0.8 }}
                    animate={{ pathLength: 1, opacity: 0 }}
                    transition={{ duration: 1.5 }}
                  />
                ))}

              {activeMessage?.type === 'heartbeat' && leaderId && (
                <motion.circle
                  cx={nodeCoords[leaderId].x}
                  cy={nodeCoords[leaderId].y}
                  r={60}
                  fill="none"
                  stroke="#06b6d4"
                  strokeWidth="2"
                  initial={{ r: 60, opacity: 0.8 }}
                  animate={{ r: 90, opacity: 0 }}
                  transition={{ duration: 1.5, ease: 'easeOut' }}
                />
              )}

              {/* Peer responses */}
              {activeMessage?.type === 'peer_response' &&
                nodeCoords[activeMessage.from] &&
                nodeCoords[activeMessage.to] && (
                  <motion.line
                    x1={nodeCoords[activeMessage.from].x}
                    y1={nodeCoords[activeMessage.from].y}
                    x2={nodeCoords[activeMessage.to].x}
                    y2={nodeCoords[activeMessage.to].y}
                    stroke="#10b981"
                    strokeWidth="3"
                    strokeDasharray="5,5"
                    initial={{ pathLength: 0 }}
                    animate={{ pathLength: 1 }}
                    transition={{ duration: 0.6 }}
                  />
                )}

              {/* Nodes A, B, C */}
              {['A', 'B', 'C'].map((nodeId) => {
                const isLeader = leaderId === nodeId;
                const color = isLeader ? nodeColors.leader : nodeColors.follower;
                const coords = nodeCoords[nodeId];

                return (
                  <g key={`node-${nodeId}`}>
                    <circle
                      cx={coords.x}
                      cy={coords.y}
                      r={50}
                      fill={color.gradient}
                      style={{
                        filter: `drop-shadow(0 4px 12px ${color.shadow})`,
                      }}
                    />
                    <text
                      x={coords.x}
                      y={coords.y - 5}
                      textAnchor="middle"
                      fill="white"
                      fontSize="20"
                      fontWeight="bold"
                    >
                      Node {nodeId}
                    </text>
                    <text
                      x={coords.x}
                      y={coords.y + 15}
                      textAnchor="middle"
                      fill="white"
                      fontSize="11"
                      fontWeight="600"
                    >
                      {getNodeState(nodeId)}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          {/* Leader info */}
          <div
            style={{
              background: 'rgba(15, 23, 42, 0.6)',
              border: '1px solid rgba(71, 85, 105, 0.3)',
              borderRadius: '8px',
              padding: '1rem',
            }}
          >
            <div
              style={{
                fontSize: '10px',
                fontWeight: '700',
                color: '#64748b',
                marginBottom: '0.75rem',
                textTransform: 'uppercase',
              }}
            >
              Leader Info
            </div>
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '0.5rem',
                fontSize: '11px',
                color: '#cbd5e1',
              }}
            >
              <div>
                Leader: <strong>{leaderId ?? '-'}</strong>
              </div>
              <div>
                Term: <strong>{currentTerm ?? '-'}</strong>
              </div>
              <div>
                Last Log:{' '}
                <strong>
                  Index {lastLogIndex ?? '-'}, Term {lastLogTerm ?? '-'}
                </strong>
              </div>
            </div>
          </div>
        </div>

        {/* Logs per node */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: '1rem',
          }}
        >
          {['A', 'B', 'C'].map((nodeId) => (
            <div
              key={`log-${nodeId}`}
              style={{
                background: 'rgba(30, 41, 59, 0.8)',
                border: '1px solid rgba(71, 85, 105, 0.4)',
                borderRadius: '12px',
                padding: '1.5rem',
                backdropFilter: 'blur(10px)',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <h3
                style={{
                  fontSize: '1rem',
                  fontWeight: '700',
                  marginTop: 0,
                  marginBottom: '1rem',
                  color: leaderId === nodeId ? '#fed7aa' : '#bfdbfe',
                }}
              >
                Node {nodeId} Log
              </h3>
              <div
                style={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.75rem',
                  overflowY: 'auto',
                  maxHeight: '400px',
                }}
              >
                {nodeLogEntries[nodeId] && nodeLogEntries[nodeId].length === 0 ? (
                  <div
                    style={{
                      color: '#64748b',
                      fontSize: '12px',
                      fontStyle: 'italic',
                    }}
                  >
                    No entries yet...
                  </div>
                ) : nodeLogEntries[nodeId] ? (
                  nodeLogEntries[nodeId].map((log, idx) => (
                    <motion.div
                      key={`${nodeId}-log-${log.id}-${idx}`}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.4 }}
                      style={{
                        padding: '0.75rem',
                        borderRadius: '6px',
                        fontSize: '11px',
                        fontFamily: 'monospace',
                        background: log.committed
                          ? 'rgba(16, 185, 129, 0.15)'
                          : 'rgba(245, 158, 11, 0.15)',
                        border: log.committed
                          ? '1px solid rgba(16, 185, 129, 0.4)'
                          : '1px solid rgba(245, 158, 11, 0.4)',
                        color: log.committed ? '#10b981' : '#f59e0b',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        wordBreak: 'break-word',
                      }}
                    >
                      <span style={{ flex: 1 }}>
                        {log.value || 'Empty entry'}
                      </span>
                      {log.committed && (
                        <span style={{ fontSize: '9px', marginLeft: '0.5rem', whiteSpace: 'nowrap' }}>
                          ✓
                        </span>
                      )}
                    </motion.div>
                  ))
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Committed KV Store (State Machine) - 3 columns: Key, Field, Value */}
      {enhancedTableUI}

      {/* Legend */}
      <div
        style={{
          marginTop: 'auto',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '1rem',
          fontSize: '11px',
          paddingTop: '1.5rem',
          borderTop: '1px solid rgba(71, 85, 105, 0.3)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            color: '#cbd5e1',
          }}
        >
          <div
            style={{
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #f97316, #ef4444)',
            }}
          />
          Leader Node
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            color: '#cbd5e1',
          }}
        >
          <div
            style={{
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #3b82f6, #06b6d4)',
            }}
          />
          Follower Node
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            color: '#cbd5e1',
          }}
        >
          <div style={{ width: '12px', height: '2px', background: '#06b6d4' }} />
          Heartbeat (Cyan)
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            color: '#cbd5e1',
          }}
        >
          <div style={{ width: '12px', height: '2px', background: '#10b981' }} />
          Peer Response (Green)
        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  );
};

export default RaftVisualizationWithWebSocket;