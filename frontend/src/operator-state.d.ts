import type { Plan } from './operator-api';
export function restoreSavedSelection(
  runs: ReadonlyArray<{run_id: string}>, storage: Storage, open: (id: string) => Promise<void>,
): Promise<void> | void;
export const terminal: Set<string>;
export function statusLabel(status: string): string;
export function canExecute(args: { plan: Plan | null; confirmed: boolean; busy: boolean; uncertain: boolean; now: number }): boolean;
