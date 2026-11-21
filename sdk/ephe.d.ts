export {};

declare global {
  interface EpheEvent {
    event: string;
    data: unknown;
  }

  interface EpheStorage {
    get(key: string): Promise<unknown>;
    set(key: string, value: unknown): Promise<void>;
  }

  interface EpheClient {
    storage: EpheStorage;
    callTool(name: string, args?: Record<string, unknown>): Promise<string>;
    subscribe(listener: (event: EpheEvent) => void): () => void;
  }

  const ephe: EpheClient;
}
