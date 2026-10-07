import React, { useEffect, useMemo, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Toggle } from '@/components/ui/Toggle'
import { api } from '@/services/api'
import { robotV2Service } from '@/services/robotV2Service'
import { fmtErr } from '@/pages/robots-v2/formatters'

type ApiToken = {
    id: number
    name?: string
    token_type?: { typeName?: string }
}

export type SaveAsRobotModalProps = {
    open: boolean
    onClose: () => void
    runId: number
    defaultName: string
    suggestedTokenId?: number | null
    runAlreadyBound?: boolean
    onSaved: (robotId: number) => void
}

export function SaveAsRobotModal({
    open,
    onClose,
    runId,
    defaultName,
    suggestedTokenId,
    runAlreadyBound = false,
    onSaved,
}: SaveAsRobotModalProps) {
    const [name, setName] = useState(defaultName)
    const [tokenId, setTokenId] = useState<number | null>(suggestedTokenId ?? null)
    const [attachRun, setAttachRun] = useState(!runAlreadyBound)
    const [tokens, setTokens] = useState<ApiToken[]>([])
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        if (!open) return
        setName(defaultName)
        setTokenId(suggestedTokenId ?? null)
        setAttachRun(!runAlreadyBound)
        setError(null)
    }, [open, defaultName, suggestedTokenId, runAlreadyBound])

    useEffect(() => {
        if (!open) return
        let cancelled = false
        void (async () => {
            try {
                const { data } = await api.post<{ keys?: ApiToken[] }>('/apikey/data', {})
                if (!cancelled) setTokens(Array.isArray(data?.keys) ? data.keys : [])
            } catch {
                if (!cancelled) setTokens([])
            }
        })()
        return () => {
            cancelled = true
        }
    }, [open])

    const tokenOptions = useMemo(
        () => tokens.map(t => ({
            value: String(t.id),
            label: t.name ? `${t.name} (#${t.id})` : `Ключ #${t.id}`,
        })),
        [tokens],
    )

    const submit = async () => {
        const trimmed = name.trim()
        if (!trimmed) {
            setError('Укажите имя робота')
            return
        }
        if (!tokenId) {
            setError('Выберите API-ключ')
            return
        }
        setLoading(true)
        setError(null)
        try {
            const { robotId } = await robotV2Service.saveBacktestRunAsRobot(runId, {
                name: trimmed,
                tokenId,
                attachRun: runAlreadyBound ? false : attachRun,
            })
            onSaved(robotId)
        } catch (e) {
            setError(fmtErr(e))
        } finally {
            setLoading(false)
        }
    }

    return (
        <Modal
            open={open}
            onClose={loading ? () => undefined : onClose}
            title="Сохранить как робота"
            width="520px"
        >
            <div className="robots-v2-form gin-save-as-robot">
                <label className="robots-v2-field">
                    <span>Имя</span>
                    <input
                        className="robots-v2-input"
                        value={name}
                        maxLength={50}
                        onChange={e => setName(e.target.value)}
                        disabled={loading}
                    />
                </label>
                <label className="robots-v2-field">
                    <span>API-ключ</span>
                    <Select
                        className="robots-v2-select"
                        value={tokenId != null ? String(tokenId) : ''}
                        onChange={v => setTokenId(v ? Number(v) : null)}
                        options={[{ value: '', label: 'Выберите ключ…' }, ...tokenOptions]}
                        disabled={loading || tokenOptions.length === 0}
                    />
                </label>
                {!runAlreadyBound ? (
                    <div className="robots-v2-field">
                        <Toggle
                            checked={attachRun}
                            onChange={setAttachRun}
                            label="Привязать прогон к роботу"
                            disabled={loading}
                        />
                        <small className="robots-v2-hint">
                            Прогон появится во вкладке «Бэктест» у нового робота.
                        </small>
                    </div>
                ) : (
                    <p className="robots-v2-hint">
                        Прогон уже привязан к другому роботу — будет создан только новый робот с тем же конфигом.
                    </p>
                )}
                {error ? <div className="robots-v2-banner robots-v2-banner--error">{error}</div> : null}
                <div className="dashboard-settings-actions">
                    <Button variant="ghost" onClick={onClose} disabled={loading}>
                        Отмена
                    </Button>
                    <Button loading={loading} onClick={() => void submit()}>
                        Создать робота
                    </Button>
                </div>
            </div>
        </Modal>
    )
}
