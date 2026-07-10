import React from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import type { Robot } from '@/types/robot'
import type { ValidationIssue } from '@/pages/robots/robotSettingsValidation'
import { formatRobotSessionStatus } from '@/utils/robotSessionStatus'
import { FigiSummaryPanel } from '@/pages/robots/components/FigiSummaryPanel'

type Props = {
    robot: Robot | null
    isNewRobot: boolean
    robotType: 1 | 2
    marketProfile?: 'moex' | 'crypto' | 'portfolio'
    universeMode: string
    candidatePoolCount: number
    allowedFigisCount: number
    allowedFigis: string[]
    lastPaperRun: string | null
    checkedIssues: ValidationIssue[] | null
    preview: { total_checked: number; passed: number; rejected: number } | null
    saving: boolean
    checkLoading: boolean
    previewLoading: boolean
    pipelineRunning: boolean
    onSave: () => void
    onRun: () => void
    onStop: () => void
    onDelete: () => void
    onDuplicate?: () => void
    duplicating?: boolean
    needsConfigV3Migrate?: boolean
    onMigrateConfigV3?: () => void
    migratingV3?: boolean
}

export function RobotContextPanel({
    robot,
    isNewRobot,
    robotType,
    marketProfile = 'moex',
    universeMode,
    candidatePoolCount,
    allowedFigisCount,
    allowedFigis,
    lastPaperRun,
    checkedIssues,
    preview,
    saving,
    checkLoading,
    previewLoading,
    pipelineRunning,
    onSave,
    onRun,
    onStop,
    onDelete,
    onDuplicate,
    duplicating = false,
    needsConfigV3Migrate = false,
    onMigrateConfigV3,
    migratingV3 = false,
}: Props) {
    const isActive = robot?.status === 1
    const errors = checkedIssues?.filter(i => i.severity === 'error') ?? []
    const warnings = checkedIssues?.filter(i => i.severity === 'warning') ?? []

    return (
        <aside className="robots-workspace__context">
            <Card className="robot-context-panel portfolio-panel">
                <div className="dashboard-totals-card__head">
                    <h3 className="dashboard-panel-title">Контекст</h3>
                </div>
                <div className="robot-context-panel__status">
                    <span
                        className={`robot-context-panel__indicator${isActive ? ' robot-context-panel__indicator--active' : ''}`}
                        aria-hidden
                    />
                    <div>
                        <div className="robot-context-panel__status-text">
                            {isNewRobot ? 'Новый робот' : isActive ? 'Робот активен' : 'Робот остановлен'}
                        </div>
                        {robot && Number(robot.type) === 2 && (
                            <div className="robot-context-panel__session" title={robot.last_error || undefined}>
                                {formatRobotSessionStatus(robot)}
                            </div>
                        )}
                    </div>
                </div>

                {robotType === 2 && (
                    <FigiSummaryPanel
                        candidatePoolCount={candidatePoolCount}
                        allowedFigisCount={allowedFigisCount}
                        allowedFigis={allowedFigis}
                        lastPaperRun={lastPaperRun}
                        universeMode={universeMode}
                        market={marketProfile === 'crypto' ? 'crypto' : 'moex'}
                    />
                )}

                {preview && robotType === 2 && (
                    <div className="robot-context-panel__preview-stats">
                        <div className="robot-context-panel__preview-title">
                            Результат проверки {marketProfile === 'crypto' ? 'отбора монет' : 'П2'}
                        </div>
                        <div className="robot-context-panel__preview-row">
                            <span>Проверено</span>
                            <span className="mono">{preview.total_checked}</span>
                        </div>
                        <div className="robot-context-panel__preview-row">
                            <span>Прошли</span>
                            <span className="mono robot-context-panel__ok">{preview.passed}</span>
                        </div>
                        <div className="robot-context-panel__preview-row">
                            <span>Отклонено</span>
                            <span className="mono">{preview.rejected}</span>
                        </div>
                    </div>
                )}

                {(errors.length > 0 || warnings.length > 0) && (
                    <div className="robot-context-panel__validation">
                        <div className="robot-context-panel__preview-title">Валидация</div>
                        <ul className="robot-settings-validation">
                            {errors.map(issue => (
                                <li
                                    key={issue.id}
                                    className="robot-settings-validation__item robot-settings-validation__item--error"
                                >
                                    {issue.message}
                                </li>
                            ))}
                            {warnings.map(issue => (
                                <li
                                    key={issue.id}
                                    className="robot-settings-validation__item robot-settings-validation__item--warning"
                                >
                                    {issue.message}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                <div className="robot-context-panel__actions">
                    <Button
                        size="sm"
                        variant="primary"
                        glow
                        className="robot-context-panel__btn"
                        loading={saving}
                        onClick={onSave}
                    >
                        {isNewRobot ? 'Создать' : 'Сохранить'}
                    </Button>
                </div>
                {!isNewRobot && robot && (
                    <div className="robot-context-panel__actions">
                        <Button
                            size="sm"
                            variant="secondary"
                            className="robot-context-panel__btn"
                            loading={pipelineRunning || checkLoading || previewLoading || saving}
                            disabled={pipelineRunning}
                            onClick={onRun}
                        >
                            ▶ Запустить
                        </Button>
                        {isActive && (
                            <Button size="sm" variant="ghost" className="robot-context-panel__btn" onClick={onStop}>
                                ⏸ Остановить
                            </Button>
                        )}
                    </div>
                )}
                {needsConfigV3Migrate && onMigrateConfigV3 && (
                    <Button
                        size="sm"
                        variant="secondary"
                        className="robot-context-panel__btn robot-context-panel__btn--full"
                        loading={migratingV3}
                        onClick={onMigrateConfigV3}
                    >
                        Мигрировать config → v3
                    </Button>
                )}
                {!isNewRobot && robot && onDuplicate && (
                    <Button
                        size="sm"
                        variant="secondary"
                        className="robot-context-panel__btn robot-context-panel__btn--full"
                        loading={duplicating}
                        onClick={onDuplicate}
                    >
                        Дублировать робота
                    </Button>
                )}
                {!isNewRobot && robot && (
                    <Button size="sm" variant="danger" className="robot-context-panel__btn robot-context-panel__btn--full" onClick={onDelete}>
                        Удалить робота
                    </Button>
                )}

                <p className="robot-context-panel__footnote">Изменения применяются после «Сохранить»</p>
            </Card>
        </aside>
    )
}
