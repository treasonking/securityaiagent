import type { Plan } from './operator-api';
export const terminal: Set<string>;
export function statusLabel(status: string): string;
export function canExecute(args: { plan: Plan | null; confirmed: boolean; busy: boolean; uncertain: boolean; now: number }): boolean;
