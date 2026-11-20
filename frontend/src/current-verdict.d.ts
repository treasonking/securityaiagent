import type { ReactElement } from 'react';
import type { Conclusion, PastRun, Result } from './operator-api';
export function CurrentVerdict(props: { conclusion?: Conclusion }): ReactElement;
export function SavedRunButton(props: { run: PastRun; onOpen: (id: string) => void }): ReactElement;
export function ResultHeading(props: { run: Result }): ReactElement;
