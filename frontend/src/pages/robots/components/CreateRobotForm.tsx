import React from 'react'
import { Select } from '@/components/ui/Select'
import type { ValidationIssue } from '@/pages/robots/robotSettingsValidation'

type Option = { value: string; label: string }

type Props = {
    name: string
    onNameChange: (v: string) => void
    tokenId: number
    tokenOptions: Option[]
    onTokenChange: (tokenId: number) => void
    robotType: 1 | 2
    robotTypeOptions: Option[]
    onRobotTypeChange: (type: 1 | 2) => void
    /** Тип можно менять только при создании. */
    typeLocked?: boolean
    brokerLabel: string
    checkedIssues?: ValidationIssue[] | null
}

function fieldIssues(issues: ValidationIssue[] | null | undefined, field: string): ValidationIssue[] {
    return (issues || []).filter(i => i.field === field)
}

export function CreateRobotForm({
    name,
    onNameChange,
    tokenId,
    tokenOptions,
    onTokenChange,
    robotType,
    robotTypeOptions,
    onRobotTypeChange,
    typeLocked = false,
    brokerLabel,
    checkedIssues,
}: Props) {
    return (
        <>
            <div className="form-group">
                <label className="form-label">Название робота</label>
                <input
                    className="form-input cyber-input"
                    value={name}
                    onChange={e => onNameChange(e.target.value)}
                />
                {fieldIssues(checkedIssues, 'name').map(issue => (
                    <p key={issue.id} className="field-inline-error">{issue.message}</p>
                ))}
            </div>
            <div className="form-row">
                <div className="form-group">
                    <label className="form-label">Тип робота</label>
                    <div className="cyber-select-wrap">
                        {typeLocked ? (
                            <div className="gin-select gin-select--readonly" aria-readonly="true">
                                <div className="gin-select__trigger">
                                    <span className="gin-select__value">
                                        {robotTypeOptions.find(o => o.value === String(robotType))?.label
                                            || (robotType === 1 ? 'Portfolio updater' : 'Trading robot')}
                                    </span>
                                </div>
                            </div>
                        ) : (
                            <Select
                                options={robotTypeOptions.length ? robotTypeOptions : [
                                    { value: '1', label: 'Portfolio updater' },
                                    { value: '2', label: 'Trading robot' },
                                ]}
                                value={String(robotType)}
                                onChange={v => onRobotTypeChange((Number(v) === 1 ? 1 : 2))}
                            />
                        )}
                    </div>
                </div>
                <div className="form-group">
                    <label className="form-label">Токен</label>
                    <div className="cyber-select-wrap">
                        <Select
                            options={[{ value: '0', label: 'Выберите токен' }, ...tokenOptions]}
                            value={String(tokenId || 0)}
                            onChange={v => onTokenChange(Number(v || 0))}
                        />
                    </div>
                    {fieldIssues(checkedIssues, 'token').map(issue => (
                        <p key={issue.id} className="field-inline-error">{issue.message}</p>
                    ))}
                </div>
            </div>
            <div className="form-group">
                <label className="form-label">Брокер</label>
                <div className="cyber-select-wrap">
                    <div className="gin-select gin-select--readonly" aria-readonly="true">
                        <div className="gin-select__trigger">
                            <span className="gin-select__value">{brokerLabel}</span>
                        </div>
                    </div>
                </div>
            </div>
        </>
    )
}
