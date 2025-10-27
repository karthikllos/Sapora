/**
 * Sapora Electron - Main React Application
 * Zoom-like UI for video conferencing
 */

const { useState, useEffect, useRef } = React;

// ==================== COMPONENTS ====================

// Login Screen Component
function LoginScreen({ onJoin }) {
    const [serverIp, setServerIp] = useState('127.0.0.1');
    const [username, setUsername] = useState(`User-${Date.now()}`);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const handleJoin = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        try {
            const result = await window.electronAPI.startBackend({ serverIp, username });
            if (result.success) {
                onJoin({ serverIp, username });
            } else {
                setError(result.message || 'Failed to start backend');
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return React.createElement('div', { 
        style: {
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100vh',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
        }
    },
        React.createElement('div', { 
            style: {
                background: 'rgba(255,255,255,0.95)',
                padding: '3rem',
                borderRadius: '20px',
                boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
                maxWidth: '450px',
                width: '90%'
            }
        },
            React.createElement('h1', { 
                style: { 
                    fontSize: '2.5rem', 
                    marginBottom: '0.5rem', 
                    color: '#333',
                    textAlign: 'center'
                }
            }, '🎥 SAPORA'),
            React.createElement('p', { 
                style: { 
                    color: '#666', 
                    marginBottom: '2rem',
                    textAlign: 'center'
                }
            }, 'LAN Video Conferencing'),
            
            React.createElement('form', { onSubmit: handleJoin },
                React.createElement('div', { style: { marginBottom: '1.5rem' } },
                    React.createElement('label', { 
                        style: { 
                            display: 'block', 
                            marginBottom: '0.5rem', 
                            color: '#333',
                            fontWeight: '500'
                        }
                    }, 'Server IP'),
                    React.createElement('input', {
                        type: 'text',
                        value: serverIp,
                        onChange: (e) => setServerIp(e.target.value),
                        required: true,
                        style: {
                            width: '100%',
                            padding: '0.75rem',
                            border: '2px solid #ddd',
                            borderRadius: '8px',
                            fontSize: '1rem',
                            transition: 'border 0.2s'
                        }
                    })
                ),
                React.createElement('div', { style: { marginBottom: '1.5rem' } },
                    React.createElement('label', { 
                        style: { 
                            display: 'block', 
                            marginBottom: '0.5rem', 
                            color: '#333',
                            fontWeight: '500'
                        }
                    }, 'Your Name'),
                    React.createElement('input', {
                        type: 'text',
                        value: username,
                        onChange: (e) => setUsername(e.target.value),
                        required: true,
                        style: {
                            width: '100%',
                            padding: '0.75rem',
                            border: '2px solid #ddd',
                            borderRadius: '8px',
                            fontSize: '1rem'
                        }
                    })
                ),
                error && React.createElement('div', {
                    style: {
                        padding: '0.75rem',
                        background: '#fee',
                        color: '#c33',
                        borderRadius: '8px',
                        marginBottom: '1rem',
                        fontSize: '0.9rem'
                    }
                }, error),
                React.createElement('button', {
                    type: 'submit',
                    disabled: loading,
                    style: {
                        width: '100%',
                        padding: '1rem',
                        background: loading ? '#999' : '#667eea',
                        color: 'white',
                        border: 'none',
                        borderRadius: '8px',
                        fontSize: '1.1rem',
                        fontWeight: 'bold',
                        cursor: loading ? 'not-allowed' : 'pointer',
                        transition: 'background 0.2s'
                    }
                }, loading ? 'Connecting...' : 'Join Meeting')
            )
        )
    );
}

// Main Meeting Room Component
function MeetingRoom({ config }) {
    const [socket, setSocket] = useState(null);
    const [connected, setConnected] = useState(false);
    const [state, setState] = useState({
        muted: false,
        videoOff: false,
        chatOpen: false,
        screenSharing: false
    });
    const [users, setUsers] = useState([]);
    const [messages, setMessages] = useState([]);
    const [newMessage, setNewMessage] = useState('');

    // Connect to WebSocket
    useEffect(() => {
        const sock = io('http://localhost:5556');
        
        sock.on('connect', () => {
            console.log('Connected to backend');
            setConnected(true);
        });

        sock.on('disconnect', () => {
            console.log('Disconnected from backend');
            setConnected(false);
        });

        sock.on('client_ready', (data) => {
            console.log('Client ready:', data);
            setState(prev => ({ ...prev, ...data.state }));
        });

        sock.on('user_list_update', (data) => {
            setUsers(data.users || []);
        });

        sock.on('chat_message', (data) => {
            setMessages(prev => [...prev, data]);
        });

        sock.on('audio_status', (data) => {
            setState(prev => ({ ...prev, audioStreaming: data.streaming }));
        });

        sock.on('video_status', (data) => {
            setState(prev => ({ ...prev, videoStreaming: data.streaming }));
        });

        sock.on('mute_status', (data) => {
            setState(prev => ({ ...prev, muted: data.muted }));
        });

        setSocket(sock);

        return () => {
            sock.disconnect();
        };
    }, []);

    const toggleAudio = () => {
        if (socket) {
            if (state.audioStreaming) {
                socket.emit('stop_audio');
            } else {
                socket.emit('start_audio');
            }
        }
    };

    const toggleVideo = () => {
        if (socket) {
            if (state.videoStreaming) {
                socket.emit('stop_video');
            } else {
                socket.emit('start_video');
            }
        }
    };

    const toggleMute = () => {
        if (socket) {
            socket.emit('toggle_mute');
        }
    };

    const toggleChat = () => {
        setState(prev => ({ ...prev, chatOpen: !prev.chatOpen }));
    };

    const sendMessage = (e) => {
        e.preventDefault();
        if (socket && newMessage.trim()) {
            socket.emit('send_chat', { message: newMessage });
            setNewMessage('');
        }
    };

    const leaveMeeting = async () => {
        if (confirm('Are you sure you want to leave the meeting?')) {
            await window.electronAPI.stopBackend();
            window.location.reload();
        }
    };

    return React.createElement('div', { 
        style: { 
            display: 'flex', 
            flexDirection: 'column', 
            height: '100vh',
            background: '#1a1a1a'
        }
    },
        // Top bar
        React.createElement('div', {
            style: {
                background: '#2a2a2a',
                padding: '0.75rem 1.5rem',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                borderBottom: '1px solid #333'
            }
        },
            React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: '1rem' } },
                React.createElement('h2', { style: { fontSize: '1.2rem', color: '#fff' } }, '🎥 Sapora'),
                React.createElement('span', { 
                    style: { 
                        padding: '0.25rem 0.75rem',
                        background: connected ? '#22c55e' : '#ef4444',
                        borderRadius: '12px',
                        fontSize: '0.8rem'
                    }
                }, connected ? '● Connected' : '● Disconnected')
            ),
            React.createElement('div', { style: { color: '#999', fontSize: '0.9rem' } },
                `${config.username} @ ${config.serverIp}`
            )
        ),

        // Main content area
        React.createElement('div', {
            style: {
                flex: 1,
                display: 'flex',
                position: 'relative',
                overflow: 'hidden'
            }
        },
            // Video grid
            React.createElement('div', {
                style: {
                    flex: 1,
                    display: 'grid',
                    gridTemplateColumns: users.length <= 1 ? '1fr' : users.length <= 4 ? 'repeat(2, 1fr)' : 'repeat(3, 1fr)',
                    gap: '1rem',
                    padding: '1rem',
                    background: '#1a1a1a',
                    marginRight: state.chatOpen ? '350px' : '0',
                    transition: 'margin-right 0.3s'
                }
            },
                React.createElement('div', {
                    style: {
                        background: '#2a2a2a',
                        borderRadius: '12px',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        minHeight: '300px',
                        position: 'relative'
                    }
                },
                    React.createElement('div', {
                        style: {
                            width: '80px',
                            height: '80px',
                            borderRadius: '50%',
                            background: '#667eea',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '2rem',
                            marginBottom: '1rem'
                        }
                    }, config.username.charAt(0).toUpperCase()),
                    React.createElement('div', { style: { color: '#fff', fontWeight: '500' } }, config.username + ' (You)'),
                    React.createElement('div', { 
                        style: { 
                            color: '#999', 
                            fontSize: '0.9rem',
                            marginTop: '0.5rem'
                        }
                    }, state.muted ? '🔇 Muted' : '🎤 Unmuted')
                ),

                users.filter(u => u.username !== config.username).map((user, idx) =>
                    React.createElement('div', {
                        key: idx,
                        style: {
                            background: '#2a2a2a',
                            borderRadius: '12px',
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                            minHeight: '300px'
                        }
                    },
                        React.createElement('div', {
                            style: {
                                width: '80px',
                                height: '80px',
                                borderRadius: '50%',
                                background: '#764ba2',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                fontSize: '2rem',
                                marginBottom: '1rem'
                            }
                        }, user.username.charAt(0).toUpperCase()),
                        React.createElement('div', { style: { color: '#fff', fontWeight: '500' } }, user.username)
                    )
                )
            ),

            // Chat panel
            state.chatOpen && React.createElement('div', {
                style: {
                    position: 'absolute',
                    right: 0,
                    top: 0,
                    bottom: 0,
                    width: '350px',
                    background: '#2a2a2a',
                    borderLeft: '1px solid #333',
                    display: 'flex',
                    flexDirection: 'column'
                }
            },
                React.createElement('div', {
                    style: {
                        padding: '1rem',
                        borderBottom: '1px solid #333',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center'
                    }
                },
                    React.createElement('h3', { style: { fontSize: '1.1rem' } }, '💬 Chat'),
                    React.createElement('button', {
                        onClick: toggleChat,
                        style: {
                            background: 'transparent',
                            border: 'none',
                            color: '#fff',
                            fontSize: '1.5rem',
                            cursor: 'pointer',
                            padding: '0.25rem'
                        }
                    }, '×')
                ),
                React.createElement('div', {
                    style: {
                        flex: 1,
                        overflowY: 'auto',
                        padding: '1rem'
                    }
                },
                    messages.map((msg, idx) =>
                        React.createElement('div', {
                            key: idx,
                            style: {
                                marginBottom: '1rem',
                                padding: '0.75rem',
                                background: '#333',
                                borderRadius: '8px'
                            }
                        },
                            React.createElement('div', {
                                style: {
                                    fontWeight: 'bold',
                                    marginBottom: '0.25rem',
                                    color: '#667eea'
                                }
                            }, msg.sender),
                            React.createElement('div', { style: { color: '#ddd' } }, msg.message)
                        )
                    )
                ),
                React.createElement('form', {
                    onSubmit: sendMessage,
                    style: {
                        padding: '1rem',
                        borderTop: '1px solid #333',
                        display: 'flex',
                        gap: '0.5rem'
                    }
                },
                    React.createElement('input', {
                        type: 'text',
                        value: newMessage,
                        onChange: (e) => setNewMessage(e.target.value),
                        placeholder: 'Type a message...',
                        style: {
                            flex: 1,
                            padding: '0.75rem',
                            background: '#333',
                            border: 'none',
                            borderRadius: '8px',
                            color: '#fff'
                        }
                    }),
                    React.createElement('button', {
                        type: 'submit',
                        style: {
                            padding: '0.75rem 1.5rem',
                            background: '#667eea',
                            border: 'none',
                            borderRadius: '8px',
                            color: '#fff',
                            cursor: 'pointer',
                            fontWeight: 'bold'
                        }
                    }, 'Send')
                )
            )
        ),

        // Bottom controls bar
        React.createElement('div', {
            style: {
                background: '#2a2a2a',
                padding: '1rem',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                gap: '1rem',
                borderTop: '1px solid #333'
            }
        },
            React.createElement('button', {
                onClick: toggleMute,
                style: {
                    width: '60px',
                    height: '60px',
                    borderRadius: '50%',
                    background: state.muted ? '#ef4444' : '#3a3a3a',
                    border: 'none',
                    color: '#fff',
                    fontSize: '1.5rem',
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                },
                title: state.muted ? 'Unmute' : 'Mute'
            }, state.muted ? '🔇' : '🎤'),

            React.createElement('button', {
                onClick: toggleVideo,
                style: {
                    width: '60px',
                    height: '60px',
                    borderRadius: '50%',
                    background: state.videoOff ? '#ef4444' : '#3a3a3a',
                    border: 'none',
                    color: '#fff',
                    fontSize: '1.5rem',
                    cursor: 'pointer'
                },
                title: state.videoOff ? 'Start Video' : 'Stop Video'
            }, state.videoOff ? '📹' : '📹'),

            React.createElement('button', {
                onClick: toggleChat,
                style: {
                    width: '60px',
                    height: '60px',
                    borderRadius: '50%',
                    background: state.chatOpen ? '#667eea' : '#3a3a3a',
                    border: 'none',
                    color: '#fff',
                    fontSize: '1.5rem',
                    cursor: 'pointer'
                },
                title: 'Toggle Chat'
            }, '💬'),

            React.createElement('button', {
                onClick: leaveMeeting,
                style: {
                    width: '60px',
                    height: '60px',
                    borderRadius: '50%',
                    background: '#ef4444',
                    border: 'none',
                    color: '#fff',
                    fontSize: '1.5rem',
                    cursor: 'pointer',
                    fontWeight: 'bold'
                },
                title: 'Leave Meeting'
            }, '📞')
        )
    );
}

// Main App Component
function App() {
    const [joined, setJoined] = useState(false);
    const [config, setConfig] = useState(null);

    const handleJoin = (joinConfig) => {
        setConfig(joinConfig);
        setJoined(true);
    };

    return joined 
        ? React.createElement(MeetingRoom, { config })
        : React.createElement(LoginScreen, { onJoin: handleJoin });
}

// Render the app
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(React.createElement(App));

console.log('[Renderer] App initialized');
