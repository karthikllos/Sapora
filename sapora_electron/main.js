/**
 * Sapora Electron - Main Process
 * Manages Python backend, window creation, and IPC
 */

const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

let mainWindow;
let pythonProcess = null;
let serverIp = '127.0.0.1';
let username = `User-${process.pid}`;

// Development mode flag
const isDev = process.argv.includes('--dev');

/**
 * Create the main application window
 */
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    title: 'Sapora - LAN Video Conferencing',
    backgroundColor: '#1a1a1a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false,
      webSecurity: true
    },
    icon: path.join(__dirname, 'assets', 'icon.png'),
    frame: true,
    show: false
  });

  // Load the renderer
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  // Show window when ready
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    mainWindow.focus();
    
    // Open DevTools in development mode
    if (isDev) {
      mainWindow.webContents.openDevTools();
    }
  });

  // Handle window close
  mainWindow.on('close', (e) => {
    if (pythonProcess) {
      e.preventDefault();
      stopPythonBackend();
      setTimeout(() => {
        mainWindow.destroy();
      }, 500);
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

/**
 * Start Python client backend
 */
function startPythonBackend(config) {
  return new Promise((resolve, reject) => {
    const { serverIp: ip, username: user } = config;
    serverIp = ip;
    username = user;

    // Find Python executable
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    
    // Path to client_main.py
    const clientPath = path.join(__dirname, '..', 'client', 'client_main.py');
    
    // Check if client_main.py exists
    if (!fs.existsSync(clientPath)) {
      reject(new Error(`client_main.py not found at ${clientPath}`));
      return;
    }

    console.log(`[Main] Starting Python backend: ${pythonCmd} ${clientPath}`);
    console.log(`[Main] Server IP: ${serverIp}, Username: ${username}`);

    // Spawn Python process
    pythonProcess = spawn(pythonCmd, [
      clientPath,
      serverIp,
      '--username', username,
      '--websocket-port', '5556'
    ], {
      cwd: path.join(__dirname, '..'),
      stdio: ['pipe', 'pipe', 'pipe']
    });

    let startupOutput = '';
    let ready = false;

    pythonProcess.stdout.on('data', (data) => {
      const output = data.toString();
      console.log(`[Python] ${output.trim()}`);
      
      startupOutput += output;
      
      // Check if backend is ready
      if (output.includes('Sapora Client ready') || output.includes('WebSocket API')) {
        ready = true;
        resolve({ success: true, message: 'Backend started' });
      }
      
      // Send logs to renderer
      if (mainWindow) {
        mainWindow.webContents.send('python-log', output);
      }
    });

    pythonProcess.stderr.on('data', (data) => {
      const error = data.toString();
      console.error(`[Python Error] ${error.trim()}`);
      
      if (mainWindow) {
        mainWindow.webContents.send('python-error', error);
      }
    });

    pythonProcess.on('error', (error) => {
      console.error(`[Main] Failed to start Python: ${error.message}`);
      reject(error);
    });

    pythonProcess.on('exit', (code, signal) => {
      console.log(`[Main] Python process exited with code ${code}, signal ${signal}`);
      pythonProcess = null;
      
      if (mainWindow) {
        mainWindow.webContents.send('python-exited', { code, signal });
      }
    });

    // Timeout if not ready within 10 seconds
    setTimeout(() => {
      if (!ready) {
        reject(new Error('Python backend startup timeout'));
      }
    }, 10000);
  });
}

/**
 * Stop Python client backend
 */
function stopPythonBackend() {
  if (pythonProcess) {
    console.log('[Main] Stopping Python backend...');
    
    try {
      // Send SIGTERM for graceful shutdown
      pythonProcess.kill('SIGTERM');
      
      // Force kill after 2 seconds if still running
      setTimeout(() => {
        if (pythonProcess) {
          console.log('[Main] Force killing Python process...');
          pythonProcess.kill('SIGKILL');
          pythonProcess = null;
        }
      }, 2000);
    } catch (error) {
      console.error(`[Main] Error stopping Python: ${error.message}`);
    }
  }
}

/**
 * IPC Handlers
 */

// Start backend with configuration
ipcMain.handle('start-backend', async (event, config) => {
  try {
    const result = await startPythonBackend(config);
    return result;
  } catch (error) {
    return { success: false, message: error.message };
  }
});

// Stop backend
ipcMain.handle('stop-backend', async () => {
  stopPythonBackend();
  return { success: true };
});

// Get backend status
ipcMain.handle('get-backend-status', async () => {
  return {
    running: pythonProcess !== null,
    serverIp,
    username
  };
});

// Open file dialog for file uploads
ipcMain.handle('select-file', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: [
      { name: 'All Files', extensions: ['*'] }
    ]
  });
  
  if (!result.canceled && result.filePaths.length > 0) {
    return { success: true, path: result.filePaths[0] };
  }
  
  return { success: false };
});

// Select save directory for downloads
ipcMain.handle('select-directory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });
  
  if (!result.canceled && result.filePaths.length > 0) {
    return { success: true, path: result.filePaths[0] };
  }
  
  return { success: false };
});

// Minimize window
ipcMain.handle('minimize-window', () => {
  if (mainWindow) {
    mainWindow.minimize();
  }
});

// Maximize/restore window
ipcMain.handle('maximize-window', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.restore();
    } else {
      mainWindow.maximize();
    }
  }
});

// Close window (triggers cleanup)
ipcMain.handle('close-window', () => {
  if (mainWindow) {
    mainWindow.close();
  }
});

/**
 * App lifecycle
 */

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  stopPythonBackend();
  
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  stopPythonBackend();
});

// Handle uncaught exceptions
process.on('uncaughtException', (error) => {
  console.error('[Main] Uncaught exception:', error);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('[Main] Unhandled rejection:', reason);
});
