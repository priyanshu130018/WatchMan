export const year = (d?: string) => d?.slice(0,4) || '—';
export const rating = (n?: number) => typeof n === 'number' ? n.toFixed(1) : '—';
export const runtime = (n?: number) => n ? `${Math.floor(n/60)}h ${n%60}m` : '—';
