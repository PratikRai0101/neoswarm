export {};

declare global {
  namespace JSX {
    interface IntrinsicElements {
      webview: React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement> & {
          src?: string;
          preload?: string;
          partition?: string;
          allowpopups?: string;
          nodeintegration?: string;
          webpreferences?: string;
          useragent?: string;
        },
        HTMLElement
      >;
    }
  }

  interface NeoSwarmUpdateInfo {
    version: string;
    releaseDate?: string;
    releaseNotes?: string | Array<{ version: string; note: string }>;
  }

  interface NeoSwarmDownloadProgress {
    bytesPerSecond: number;
    percent: number;
    transferred: number;
    total: number;
  }

  interface NeoSwarmAPI {
    getBackendPort: () => number;
    getWebviewPreloadPath: () => string;
    getAppVersion: () => Promise<string>;
    getUpdateStatus: () => Promise<{ status: string; info: any; error: string | null }>;
    checkForUpdates: () => Promise<{ success: boolean; version?: string; error?: string }>;
    downloadUpdate: () => Promise<{ success: boolean; error?: string }>;
    installUpdate: () => Promise<void>;
    onUpdateAvailable: (cb: (info: NeoSwarmUpdateInfo) => void) => () => void;
    onUpdateNotAvailable: (cb: (info: NeoSwarmUpdateInfo) => void) => () => void;
    onDownloadProgress: (cb: (progress: NeoSwarmDownloadProgress) => void) => () => void;
    onUpdateDownloaded: (cb: (info: NeoSwarmUpdateInfo) => void) => () => void;
    onUpdateError: (cb: (message: string) => void) => () => void;
    onWebviewNewWindow: (cb: (url: string, webContentsId: number) => void) => () => void;
  }

  interface Window {
    __NEOSWARM_PORT__: number;
    __OPENSWARM_PORT__: number; // backward compat
    neoswarm: NeoSwarmAPI;
  }
}
