import type { ConnectionState, TaskEvent } from "../types";

interface TimelineProps { events: TaskEvent[]; connection: ConnectionState; }

export function Timeline({ events, connection }: TimelineProps) {
  return <section aria-label="timeline"><h2>Timeline ({connection})</h2><ol>{[...events].sort((a, b) => a.sequence - b.sequence).map((event) => <li key={event.sequence}>{event.type} #{event.sequence}</li>)}</ol></section>;
}
