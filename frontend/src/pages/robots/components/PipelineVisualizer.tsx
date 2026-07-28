import React from 'react'

export type RobotEditorStage = 'general' | 'p1' | 'p2' | 'p3' | 'risk'

export type PipelineVisualizerNode = {
    id: RobotEditorStage
    title: string
    hidden?: boolean
}

type Props = {
    nodes: PipelineVisualizerNode[]
    activeStage: RobotEditorStage
    onStageChange: (stage: RobotEditorStage) => void
    /** Compact segmented tabs for narrow layouts. */
    variant?: 'default' | 'segmented'
}

function StageIcon({ stage }: { stage: RobotEditorStage }) {
    const common = {
        className: 'pipeline-visualizer__icon-svg',
        viewBox: '0 0 24 24',
        fill: 'none',
        stroke: 'currentColor',
        strokeWidth: 1.75,
        strokeLinecap: 'round' as const,
        strokeLinejoin: 'round' as const,
        'aria-hidden': true,
    }
    switch (stage) {
        case 'general':
            return (
                <svg {...common}>
                    <circle cx="12" cy="12" r="3" />
                    <path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6" />
                </svg>
            )
        case 'p1':
            return (
                <svg {...common}>
                    <circle cx="12" cy="12" r="2" />
                    <path d="M12 4a8 8 0 0 1 8 8M12 7a5 5 0 0 1 5 5" />
                    <path d="M4.5 9.5 3 8.2M6.2 6.2 4.9 4.7M9.5 4.5 8.2 3" />
                </svg>
            )
        case 'p2':
            return (
                <svg {...common}>
                    <path d="M4 6h16M7 12h10M10 18h4" />
                </svg>
            )
        case 'p3':
            return (
                <svg {...common}>
                    <path d="M13 3 5.5 13.5H12l-1 7.5L18.5 10.5H12L13 3z" />
                </svg>
            )
        case 'risk':
            return (
                <svg {...common}>
                    <path d="M12 3 5 6.5v5.2c0 4.3 2.9 7.4 7 8.3 4.1-.9 7-4 7-8.3V6.5L12 3z" />
                    <path d="M12 10v3.5M12 16.2h.01" />
                </svg>
            )
        default:
            return null
    }
}

export function PipelineVisualizer({
    nodes,
    activeStage,
    onStageChange,
    variant = 'default',
}: Props) {
    const visible = nodes.filter(n => !n.hidden)
    if (!visible.length) return null

    const segmented = variant === 'segmented'

    return (
        <nav
            className={`pipeline-visualizer${segmented ? ' pipeline-visualizer--segmented' : ''}`}
            aria-label="Этапы настройки робота"
        >
            <div className="pipeline-visualizer__track" role={segmented ? 'tablist' : undefined}>
                {visible.map((node, idx) => (
                    <React.Fragment key={node.id}>
                        {!segmented && idx > 0 && (
                            <span className="pipeline-visualizer__connector" aria-hidden />
                        )}
                        <button
                            type="button"
                            role={segmented ? 'tab' : undefined}
                            className={`pipeline-visualizer__node${
                                activeStage === node.id ? ' pipeline-visualizer__node--active' : ''
                            }`}
                            onClick={() => onStageChange(node.id)}
                            aria-current={activeStage === node.id ? 'step' : undefined}
                            aria-selected={segmented ? activeStage === node.id : undefined}
                            aria-label={node.title}
                            title={node.title}
                        >
                            <span className="pipeline-visualizer__icon" aria-hidden>
                                <StageIcon stage={node.id} />
                            </span>
                            <span className="pipeline-visualizer__title">{node.title}</span>
                        </button>
                    </React.Fragment>
                ))}
            </div>
        </nav>
    )
}
