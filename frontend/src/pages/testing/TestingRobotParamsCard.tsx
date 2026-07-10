import React from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { brokerTypeLabel } from '@/modules/robots/config/brokerImmutability'
import { PollFrequencyField } from '@/pages/testing/refactored/components/setup/PollFrequencyField'

export type TestingRobotParamsCardProps = {
    brokerType: string
    /** Не нужен при hideBroker — брокер задаётся рынком в BaseConfigPanel. */
    onBrokerTypeChange?: (v: string) => void
    pollValue?: number
    onPollValueChange?: (v: number) => void
    pollUnit?: 'minutes' | 'hours'
    onPollUnitChange?: (u: 'minutes' | 'hours') => void
    onConfigDirty: () => void
    createName?: string
    onCreateNameChange?: (v: string) => void
    createTokenId?: number | null
    onCreateTokenIdChange?: (id: number | null) => void
    createTokenOptions?: Array<{ value: string; label: string }>
    onCreateRobot?: () => void
    creatingRobot?: boolean
    brokerTypeLocked?: boolean
    onBrokerTypeChangeBlocked?: () => void
    isCrypto?: boolean
    brokerOptions?: Array<{ value: string; label: string }>
    /** Скрыть выбор брокера (определяется рынком в BaseConfigPanel). */
    hideBroker?: boolean
    /** Короткий заголовок без «брокер» (AdvancedPanel). */
    compactTitle?: boolean
    /** Скрыть частоту опроса (перенесена в SignalGenerationPanel). */
    hidePoll?: boolean
}

/** Broker + poll schedule + create robot (MOEX/crypto extended fields — в T2.3/T2.4). */
export function TestingRobotParamsCard({
    brokerType,
    onBrokerTypeChange,
    pollValue,
    onPollValueChange,
    pollUnit,
    onPollUnitChange,
    onConfigDirty,
    createName = '',
    onCreateNameChange,
    createTokenId = null,
    onCreateTokenIdChange,
    createTokenOptions = [],
    onCreateRobot,
    creatingRobot = false,
    brokerTypeLocked = false,
    onBrokerTypeChangeBlocked,
    isCrypto = false,
    brokerOptions,
    hideBroker = false,
    compactTitle = false,
    hidePoll = false,
}: TestingRobotParamsCardProps) {
    const resolvedBrokerOptions =
        brokerOptions ??
        (isCrypto
            ? [{ value: 'bybit', label: brokerTypeLabel('bybit') }]
            : [
                  { value: 'tinvest', label: brokerTypeLabel('tinvest') },
                  { value: 'sandbox', label: brokerTypeLabel('sandbox') },
              ])
    return (
        <Card className="mb-6 cyber-form-card testing-cyber-card">
            <h3 className="card__section-title pipeline-title">
                <span className="cyber-bracket">[</span>
                {compactTitle ? 'ОПРОС И СОЗДАНИЕ РОБОТА' : 'БРОКЕР И РАСПИСАНИЕ'}
                <span className="cyber-bracket">]</span>
            </h3>
            <div className="testing-robot-grid">
                {!hideBroker && (
                <div className="form-group testing-form-group-flat">
                    <label className="form-label">Брокер</label>
                    <Select
                        disabled={brokerTypeLocked}
                        options={[...resolvedBrokerOptions]}
                        value={brokerType}
                        onChange={v => {
                            if (brokerTypeLocked) {
                                onBrokerTypeChangeBlocked?.()
                                return
                            }
                            onBrokerTypeChange?.(String(v || 'tinvest'))
                            onConfigDirty()
                        }}
                    />
                    {brokerTypeLocked && (
                        <p className="testing-create-robot-hint">
                            Брокер задаётся при создании робота и не меняется.
                        </p>
                    )}
                </div>
                )}
                {!hidePoll && pollValue != null && onPollValueChange && pollUnit && onPollUnitChange && (
                <PollFrequencyField
                    pollValue={pollValue}
                    onPollValueChange={onPollValueChange}
                    pollUnit={pollUnit}
                    onPollUnitChange={onPollUnitChange}
                    onConfigDirty={onConfigDirty}
                />
                )}
                {onCreateRobot && (
                    <div className="testing-create-robot-block">
                        <p className="form-label testing-create-robot-block__title">Создать торгового робота из текущих настроек</p>
                        <div className="testing-create-robot-grid">
                            <div className="form-group testing-form-group-flat">
                                <label className="form-label">Название</label>
                                <input
                                    className="form-input"
                                    type="text"
                                    placeholder="Например, Grain TQBR v1"
                                    value={createName}
                                    onChange={e => onCreateNameChange?.(e.target.value)}
                                />
                            </div>
                            <div className="form-group testing-form-group-flat">
                                <label className="form-label">Токен</label>
                                <Select
                                    options={[
                                        { value: '', label: '— выберите токен —' },
                                        ...createTokenOptions,
                                    ]}
                                    value={createTokenId != null ? String(createTokenId) : ''}
                                    onChange={v => onCreateTokenIdChange?.(v ? Number(v) : null)}
                                />
                            </div>
                            <div className="testing-create-robot-grid__action">
                                <Button
                                    variant="secondary"
                                    loading={creatingRobot}
                                    disabled={creatingRobot || !createName.trim() || !createTokenId}
                                    onClick={() => onCreateRobot()}
                                >
                                    Создать робота
                                </Button>
                            </div>
                        </div>
                        <p className="testing-create-robot-hint">
                            Конфиг (стратегия, pipeline, риск, costs, расписание) совпадает с бэктестом. После создания
                            выберите робота в списке и запустите тест или включите live в настройках.
                        </p>
                    </div>
                )}
            </div>
        </Card>
    )
}
