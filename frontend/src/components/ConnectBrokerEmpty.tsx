import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'

type Props = {
    /** Defaults to /settings#tokens. Pass to open create-token flow in place. */
    onConnect?: () => void
}

/** First-login empty cabin: connect broker before dashboard / portfolio / robots / settings. */
export function ConnectBrokerEmpty({ onConnect }: Props) {
    const navigate = useNavigate()
    return (
        <div className="dashboard-first-run-wrap">
            <Card className="dashboard-totals-card dashboard-first-run">
                <h2 className="dashboard-first-run__title">Нужен токен брокера</h2>
                <p className="dashboard-first-run__text">
                    Без него нет счетов, портфеля и роботов.
                </p>
                <div className="dashboard-first-run__actions">
                    <Button
                        type="button"
                        variant="primary"
                        size="lg"
                        className="dashboard-first-run__primary"
                        onClick={() => {
                            if (onConnect) onConnect()
                            else navigate('/settings#tokens')
                        }}
                    >
                        Подключить
                    </Button>
                </div>
            </Card>
        </div>
    )
}
