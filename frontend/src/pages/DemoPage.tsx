import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { StatTile } from '@/components/ui/StatTile'

///@ Учебный пример портфеля и прогона. Цифры фиксированные, это не счёт пользователя.
export default function DemoPage() {
    const navigate = useNavigate()

    return (
        <div className="login-page">
            <div className="login-demo">
                <div className="login-demo__head">
                    <div className="login-logo" data-text="GIN">
                        <span className="logo-g">G</span>
                        <span className="logo-i">I</span>
                        <span className="logo-n">N</span>
                    </div>
                    <p className="login-demo__kicker">Учебный пример. Это не ваш счёт и не рекомендация.</p>
                </div>

                <div className="login-demo__grid">
                    <Card className="dashboard-totals-card">
                        <div className="dashboard-totals-card__head">
                            <h2 className="dashboard-panel-title">Портфель</h2>
                        </div>
                        <div className="portfolio-stats-grid dashboard-summary-grid">
                            <StatTile label="Стоимость" value="1 840 000 ₽" />
                            <StatTile label="Свои деньги" value="1 500 000 ₽" />
                            <StatTile label="Доходность к своим" value="+22,7%" valueClassName="color-up" />
                            <StatTile label="Просадка" value="−11,4%" valueClassName="color-down" />
                        </div>
                        <p className="robots-v2-hint login-demo__note">
                            В приложении брокера эти 340 000 ₽ легко смешать с вводами. Здесь доходность считается от внесённых денег.
                        </p>
                    </Card>

                    <Card className="dashboard-assets-card">
                        <div className="dashboard-assets-card__head">
                            <h2 className="dashboard-panel-title">Прогон стратегии</h2>
                        </div>
                        <div className="portfolio-stats-grid dashboard-summary-grid">
                            <StatTile label="После издержек" value="+18,2%" valueClassName="color-up" />
                            <StatTile label="IMOEX" value="+9,1%" />
                            <StatTile label="Комиссия" value="4 120 ₽" />
                            <StatTile label="НДФЛ" value="6 800 ₽" />
                        </div>
                        <p className="robots-v2-hint">Из-за чего были сделки:</p>
                        <ul className="login-demo__journal">
                            <li>SBER: цена выше средней, объём выше обычного.</li>
                            <li>GAZP: на одной свече задеты стоп и тейк — засчитан стоп.</li>
                            <li>LKOH: заявка урезана до 10% объёма бара.</li>
                        </ul>
                    </Card>
                </div>

                <div className="login-demo__actions">
                    <Button type="button" variant="primary" size="lg" onClick={() => navigate('/login?mode=register')}>
                        Зарегистрироваться
                    </Button>
                    <Button type="button" variant="ghost" size="lg" onClick={() => navigate('/login')}>
                        Войти
                    </Button>
                </div>
            </div>
            <div className="login-bg-grid" />
        </div>
    )
}
