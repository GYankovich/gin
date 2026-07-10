export type RunControlState = 'idle' | 'running' | 'success' | 'error'

export function deriveRunControlState(args: {
    running: boolean
    hasResult: boolean
    error?: string | null
}): RunControlState {
    if (args.running) return 'running'
    if (args.error) return 'error'
    if (args.hasResult) return 'success'
    return 'idle'
}

export function runControlStateLabel(state: RunControlState): string {
    if (state === 'running') return 'Выполняется'
    if (state === 'success') return 'Результат готов'
    if (state === 'error') return 'Ошибка запуска'
    return 'Ожидание запуска'
}

export function runControlSystemLabel(state: RunControlState): string {
    if (state === 'running') return 'System Running'
    if (state === 'success') return 'Result Ready'
    if (state === 'error') return 'Run Failed'
    return 'System Ready'
}
